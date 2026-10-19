#!/usr/bin/env python3
"""Benchmark Ollama pour la RTX 5070 Ti - estimation prefill/decode tok/s (proxy G_n) du Flop Network.

Usage:
  python tools/bench_ollama.py                                    # 3 runs rapides sur Hermes-4-14B
  python tools/bench_ollama.py --runs 5 --prompt-tokens 4000      # mesure prefill plus serieuse
  python tools/bench_ollama.py --minutes 60 --output-tokens 2048  # soak 1h (stabilite longue duree)
Resultats dans bench/ (CSV par run + journal GPU).
"""
import argparse
import csv
import datetime as dt
import json
import pathlib
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

DEFAULT_MODEL = "hf.co/bartowski/NousResearch_Hermes-4-14B-GGUF:Q4_K_M"
H100_SXM_IN_TPS = 17058
H100_SXM_OUT_TPS = 3694

FILLER = (
    "Inference workloads measure prefill and decode throughput on modern GPUs. "
    "The quick brown fox jumps over the lazy dog while the curious cat watches "
    "from the windowsill and the GPU fans spin at a steady pace under load. "
)


class GpuSampler(threading.Thread):
    QUERY = [
        "nvidia-smi",
        "--query-gpu=timestamp,temperature.gpu,power.draw,utilization.gpu,memory.used",
        "--format=csv,noheader,nounits",
    ]
    KEYS = ["time", "temp_c", "power_w", "util_pct", "vram_mib"]

    def __init__(self, interval: float, log_path: pathlib.Path):
        super().__init__(daemon=True)
        self.interval = interval
        self.log_path = log_path
        self.latest: dict[str, str] = {}
        self.samples: list[dict[str, str]] = []
        self._stop_event = threading.Event()

    def run(self):
        with open(self.log_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(self.KEYS)
            while not self._stop_event.is_set():
                try:
                    out = subprocess.run(
                        self.QUERY, capture_output=True, text=True, timeout=15
                    ).stdout.strip()
                    if out:
                        row = [p.strip() for p in out.split(",")]
                        self.latest = dict(zip(self.KEYS, row))
                        self.samples.append(self.latest)
                        writer.writerow(row)
                        f.flush()
                except Exception:
                    pass
                self._stop_event.wait(self.interval)

    def stop(self):
        self._stop_event.set()
        self.join(timeout=self.interval + 5)

    def peak(self, key: str) -> float:
        vals = []
        for s in self.samples:
            try:
                vals.append(float(s.get(key, "nan")))
            except ValueError:
                pass
        return max(vals) if vals else float("nan")


def build_prompt(target_tokens: int, salt: str) -> str:
    approx_chars = target_tokens * 4
    text = (salt + FILLER) * (approx_chars // len(FILLER) + 2)
    return text[:approx_chars] + (
        "\n\nContinue with a long, detailed technical essay about GPU inference "
        "benchmarking, throughput and memory bandwidth. Essay:\n"
    )


def call_ollama(api: str, model: str, prompt: str, num_predict: int, ctx: int, timeout: int):
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "num_predict": num_predict,
            "temperature": 0,
            "num_ctx": ctx,
        },
    }
    req = urllib.request.Request(
        api, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return data, time.perf_counter() - t0


def extract_metrics(data: dict) -> dict:
    prefill_tokens = data.get("prompt_eval_count") or 0
    prefill_ns = data.get("prompt_eval_duration") or 0
    decode_tokens = data.get("eval_count") or 0
    decode_ns = data.get("eval_duration") or 0
    return {
        "prefill_tokens": prefill_tokens,
        "prefill_s": prefill_ns / 1e9,
        "decode_tokens": decode_tokens,
        "decode_s": decode_ns / 1e9,
        "prefill_tps": prefill_tokens / (prefill_ns / 1e9) if prefill_ns else None,
        "decode_tps": decode_tokens / (decode_ns / 1e9) if decode_ns else None,
    }


def fmt(v):
    return f"{v:.1f}" if isinstance(v, (int, float)) else "-"


def main():
    ap = argparse.ArgumentParser(description="Benchmark Ollama prefill/decode (proxy G_n Flop)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--parallel", type=int, default=1,
                    help="requetes concurrentes par run (mesure le throughput agrege, type serveur)")
    ap.add_argument("--minutes", type=float, default=None, help="soak: boucle jusqu'a cette duree (min)")
    ap.add_argument("--prompt-tokens", type=int, default=2000)
    ap.add_argument("--output-tokens", type=int, default=512)
    ap.add_argument("--ctx", type=int, default=8192)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--gpu-interval", type=float, default=5.0)
    ap.add_argument("--api", default="http://localhost:11434/api/generate")
    args = ap.parse_args()

    out_dir = pathlib.Path(__file__).resolve().parent.parent / "bench"
    out_dir.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"ollama_bench_{stamp}.csv"
    gpu_path = out_dir / f"gpu_log_{stamp}.csv"

    print(f"Modele   : {args.model}")
    print(f"Config   : prompt~{args.prompt_tokens} tok -> sortie max {args.output_tokens} tok, ctx {args.ctx}")

    sampler = GpuSampler(args.gpu_interval, gpu_path)
    sampler.start()

    print("Warmup (chargement du modele, non compte)...")
    t0 = time.perf_counter()
    try:
        call_ollama(args.api, args.model, build_prompt(args.prompt_tokens, "[warmup] "), 32, args.ctx, args.timeout)
    except urllib.error.URLError as e:
        sampler.stop()
        raise SystemExit(f"Ollama injoignable sur {args.api} : {e}")
    print(f"Warmup termine en {time.perf_counter() - t0:.0f}s")

    # Sel propre a cette execution : sans lui, une 2e execution rejoue les memes
    # prompts et Ollama sert le prefill depuis son cache KV (prefill irrealiste).
    session = dt.datetime.now().strftime("%H%M%S")
    rows = []
    agg_decodes = []
    errors = 0
    consecutive_errors = 0
    csv_file = None
    writer = None
    run = 0
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        while True:
            run += 1
            if args.minutes is None and run > args.runs:
                break
            if args.minutes is not None and (time.perf_counter() - started) / 60 >= args.minutes:
                break
            t0 = time.perf_counter()
            futures = [
                pool.submit(
                    call_ollama,
                    args.api,
                    args.model,
                    build_prompt(args.prompt_tokens, f"[{session} run {run:04d} req {i:02d}] "),
                    args.output_tokens,
                    args.ctx,
                    args.timeout,
                )
                for i in range(max(1, args.parallel))
            ]
            results = []
            for f in futures:
                try:
                    results.append(f.result())
                except Exception as e:  # soak : on compte l'erreur et on continue
                    errors += 1
                    print(f"run {run:3d} | ERREUR requete : {type(e).__name__}: {e}")
            if not results:
                consecutive_errors += 1
                if consecutive_errors >= 10:
                    print("10 runs consecutifs en echec : arret.")
                    break
                time.sleep(10)
                continue
            consecutive_errors = 0
            batch_wall = time.perf_counter() - t0
            metrics = [extract_metrics(d) for d, _ in results]
            tot_decode = sum(m["decode_tokens"] for m in metrics)
            tot_prefill = sum(m["prefill_tokens"] for m in metrics)
            max_prefill_s = max((m["prefill_s"] for m in metrics), default=0.0)
            agg_decode = tot_decode / batch_wall if batch_wall else None
            agg_prefill = tot_prefill / max_prefill_s if max_prefill_s else None
            if agg_decode:
                agg_decodes.append(agg_decode)
            gpu = dict(sampler.latest)
            for i, ((data, wall), m) in enumerate(zip(results, metrics), start=1):
                row = {
                    "run": run,
                    "req": i if args.parallel > 1 else "",
                    "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
                    "model": args.model,
                    "prompt_tokens": args.prompt_tokens,
                    **m,
                    "wall_s": round(wall, 2),
                    "batch_wall_s": round(batch_wall, 2),
                    "agg_decode_tps": round(agg_decode, 1) if agg_decode else "",
                    "agg_prefill_tps": round(agg_prefill, 1) if agg_prefill else "",
                    "gpu_temp_c": gpu.get("temp_c", ""),
                    "gpu_power_w": gpu.get("power_w", ""),
                    "gpu_util_pct": gpu.get("util_pct", ""),
                    "vram_mib": gpu.get("vram_mib", ""),
                }
                rows.append(row)
                # ecriture au fil de l'eau : un arret brutal ne perd pas les runs deja faits
                if writer is None:
                    csv_file = open(csv_path, "w", newline="", encoding="utf-8")
                    writer = csv.DictWriter(csv_file, fieldnames=list(row.keys()))
                    writer.writeheader()
                writer.writerow(row)
                csv_file.flush()
            med_dec = statistics.median([m["decode_tps"] for m in metrics if m["decode_tps"]])
            med_pre = statistics.median([m["prefill_tps"] for m in metrics if m["prefill_tps"]])
            print(
                f"run {run:3d} | prefill {fmt(med_pre)} tok/s "
                f"(decode {fmt(med_dec)} tok/s) | {tot_decode} tok generes "
                f"| agg decode {fmt(agg_decode)} tok/s "
                f"| {gpu.get('temp_c','?')} C {gpu.get('power_w','?')}W "
                f"| VRAM {gpu.get('vram_mib','?')} MiB"
            )
            if args.minutes is not None:
                elapsed = (time.perf_counter() - started) / 60
                print(f"          soak: {elapsed:.1f}/{args.minutes} min")

    sampler.stop()
    if csv_file:
        csv_file.close()

    if not rows:
        raise SystemExit("Aucun run effectue.")

    prefill = [r["prefill_tps"] for r in rows if r["prefill_tps"]]
    decode = [r["decode_tps"] for r in rows if r["decode_tps"]]

    print("\n===== RESUME =====")
    print(f"Runs          : {len(rows)}")
    print(f"Erreurs       : {errors} requete(s)")
    print(f"CSV           : {csv_path}")
    print(f"Journal GPU   : {gpu_path}")
    if prefill:
        print(f"Prefill  med. : {statistics.median(prefill):.1f} tok/s "
              f"(min {min(prefill):.1f} / max {max(prefill):.1f})")
    if decode:
        print(f"Decode  med.  : {statistics.median(decode):.1f} tok/s "
              f"(min {min(decode):.1f} / max {max(decode):.1f})")
    if agg_decodes:
        print(f"Decode agrege med. ({args.parallel} req concurrentes) : "
              f"{statistics.median(agg_decodes):.1f} tok/s "
              f"(min {min(agg_decodes):.1f} / max {max(agg_decodes):.1f})")
    print(f"GPU pic       : {sampler.peak('temp_c'):.0f} C, {sampler.peak('power_w'):.0f} W, "
          f"VRAM {sampler.peak('vram_mib'):.0f} MiB")
    if decode:
        eq = statistics.median(decode) / H100_SXM_OUT_TPS
        print(f"\nIndice H100-eq (decode only, vs ancre SXM {H100_SXM_OUT_TPS} tok/s) : ~{eq:.3f}")
        if prefill:
            eqp = statistics.median(prefill) / H100_SXM_IN_TPS
            print(f"Indice H100-eq (prefill only, vs {H100_SXM_IN_TPS} tok/s)          : ~{eqp:.3f}")
        print(
            "\nATTENTION : modele/quant/stack differents de l'ancre officielle "
            "(gpt-oss-120b MXFP4 sur H100 SXM / vLLM).\n"
            "Cet indice est un proxy grossier pour suivre TA machine dans le temps ; "
            "la calibration G_n reelle se fera sur le reseau."
        )


if __name__ == "__main__":
    main()
