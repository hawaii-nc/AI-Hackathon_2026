"""Render the confidence/compatibility score matrices as graphs (PNG).

Reads the CSVs written by score_patients_local.py:
    confidence_scores.csv
    compatibility_scores.csv
and writes:
    graphs/score_heatmaps.png  - services x patients heatmaps (confidence + compatibility)
    graphs/top_matches.png     - per-patient top-N shelters by compatibility

No Supabase / network needed. Re-run after re-scoring to refresh the images.

    python make_score_graphs.py
    python make_score_graphs.py --top 10
"""

import argparse
import csv
import os

import matplotlib
matplotlib.use("Agg")  # headless: just write files, never open a window
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "graphs")


def load_matrix(path):
    """Return (patients, services, data) where data[patient_idx][service_idx] is a float."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.reader(f) if r]
    services = rows[0][1:]
    patients, data = [], []
    for r in rows[1:]:
        patients.append(r[0])
        data.append([float(x) for x in r[1:]])
    return patients, services, np.array(data)


def heatmaps(patients, services, conf, comp, out_path):
    n_serv = len(services)
    fig, axes = plt.subplots(
        1, 2, figsize=(11, max(8, n_serv * 0.42)), constrained_layout=True
    )
    for col, (ax, title, mat) in enumerate(
        zip(axes, ("Confidence (unweighted)", "Compatibility (weighted)"), (conf, comp))
    ):
        grid = mat.T  # rows = services, cols = patients
        im = ax.imshow(grid, cmap="RdYlGn", vmin=0, vmax=100, aspect="auto")
        ax.set_xticks(range(len(patients)))
        ax.set_xticklabels(patients, fontsize=9)
        ax.set_yticks(range(n_serv))
        ax.set_yticklabels(services if col == 0 else [], fontsize=8)
        ax.set_title(title, fontsize=12, fontweight="bold")
        for i in range(n_serv):
            for j in range(len(patients)):
                ax.text(j, i, f"{grid[i, j]:.0f}", ha="center", va="center", fontsize=8)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="score (0-100)")
    fig.suptitle("Patient x Shelter fit scores", fontsize=15, fontweight="bold")
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path


def top_matches(patients, services, comp, out_path, top_n=8):
    n = len(patients)
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 6), constrained_layout=True)
    if n == 1:
        axes = [axes]
    for ax, pi in zip(axes, range(n)):
        scores = comp[pi]
        order = np.argsort(scores)[::-1][:top_n]
        names = [services[k] for k in order]
        vals = [scores[k] for k in order]
        y = np.arange(len(names))[::-1]
        ax.barh(y, vals, color=plt.cm.RdYlGn(np.array(vals) / 100.0),
                edgecolor="#333", linewidth=0.5)
        ax.set_yticks(y)
        ax.set_yticklabels([n_ if len(n_) <= 30 else n_[:28] + "..." for n_ in names],
                           fontsize=8)
        ax.set_xlim(0, 108)
        ax.set_xlabel("compatibility")
        ax.set_title(patients[pi], fontsize=12, fontweight="bold")
        for yi, v in zip(y, vals):
            ax.text(v + 1.5, yi, f"{v:.0f}", va="center", fontsize=8)
    fig.suptitle(f"Top {top_n} shelter matches per patient (by compatibility)",
                 fontsize=14, fontweight="bold")
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Graph the score matrices.")
    ap.add_argument("--top", type=int, default=8, help="Top-N shelters per patient.")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    cp, cs, conf = load_matrix(os.path.join(HERE, "confidence_scores.csv"))
    pp, ps, comp = load_matrix(os.path.join(HERE, "compatibility_scores.csv"))
    if (cp, cs) != (pp, ps):
        raise SystemExit("confidence/compatibility CSVs disagree on their axes")

    out1 = heatmaps(cp, cs, conf, comp, os.path.join(OUT_DIR, "score_heatmaps.png"))
    out2 = top_matches(cp, cs, comp, os.path.join(OUT_DIR, "top_matches.png"), args.top)
    print("Wrote:")
    print("  " + out1)
    print("  " + out2)


if __name__ == "__main__":
    main()
