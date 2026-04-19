"""gera png da matriz de confusao do backtesting de 150 dias.

para rodar: py -m scripts.plot_backtesting_5meses
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _load_matrix(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"arquivo nao encontrado: {path}")
    matrix = pd.read_csv(path, index_col=0)
    if matrix.empty:
        raise ValueError("matriz de confusao vazia")
    return matrix


def _load_metrics(path: Path) -> tuple[int | None, float | None, float | None]:
    if not path.exists():
        return None, None, None
    df = pd.read_csv(path)
    if df.empty:
        return None, None, None
    row = df.iloc[0]
    return (
        int(row.get("n_amostras")) if pd.notna(row.get("n_amostras")) else None,
        float(row.get("kappa_ponderado")) if pd.notna(row.get("kappa_ponderado")) else None,
        float(row.get("acuracia")) if pd.notna(row.get("acuracia")) else None,
    )


def _plot_heatmap(matrix: pd.DataFrame, output_png: Path, title: str) -> None:
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns

        plt.figure(figsize=(8, 6))
        sns.heatmap(matrix, annot=True, fmt="d", cmap="Blues", cbar=True)
        plt.title(title)
        plt.xlabel("classe predita")
        plt.ylabel("classe real")
        plt.tight_layout()
        plt.savefig(output_png, dpi=220)
        plt.close()
        return
    except ImportError:
        import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 6))
    image = ax.imshow(matrix.values, cmap="Blues")
    ax.set_xticks(range(len(matrix.columns)))
    ax.set_yticks(range(len(matrix.index)))
    ax.set_xticklabels(matrix.columns, rotation=45, ha="right")
    ax.set_yticklabels(matrix.index)
    for row in range(matrix.shape[0]):
        for col in range(matrix.shape[1]):
            ax.text(col, row, str(matrix.iloc[row, col]), ha="center", va="center", color="black")
    ax.set_title(title)
    ax.set_xlabel("classe predita")
    ax.set_ylabel("classe real")
    fig.colorbar(image)
    fig.tight_layout()
    fig.savefig(output_png, dpi=220)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="gera png da matriz de confusao do backtesting 150 dias")
    parser.add_argument(
        "--matrix-csv",
        default="reports/relatorio_matriz_confusao_ana_150.csv",
        help="caminho do csv da matriz de confusao",
    )
    parser.add_argument(
        "--metrics-csv",
        default="reports/relatorio_metricas_ana_150.csv",
        help="caminho do csv de metricas",
    )
    parser.add_argument(
        "--output-png",
        default="reports/matriz_confusao_ana_150.png",
        help="caminho do png de saida",
    )
    args = parser.parse_args()

    matrix_path = Path(args.matrix_csv)
    metrics_path = Path(args.metrics_csv)
    output_path = Path(args.output_png)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    matrix = _load_matrix(matrix_path)
    n, kappa, acc = _load_metrics(metrics_path)

    title_parts = ["matriz de confusao - backtesting 150 dias"]
    if n is not None:
        title_parts.append(f"n={n}")
    if kappa is not None:
        title_parts.append(f"kappa={kappa:.3f}")
    if acc is not None:
        title_parts.append(f"acuracia={acc:.3f}")

    _plot_heatmap(matrix, output_path, " | ".join(title_parts))

    print("imagem gerada com sucesso")
    print(f"matriz: {matrix_path}")
    print(f"saida png: {output_path}")


if __name__ == "__main__":
    main()
