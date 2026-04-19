from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.processing.calculadora_risco import validar_modelo_vs_ana


def _save_confusion_png(matrix_df: pd.DataFrame, output_png: Path, title: str) -> None:
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns

        plt.figure(figsize=(8, 6))
        sns.heatmap(matrix_df, annot=True, fmt="d", cmap="Blues", cbar=True)
        plt.title(title)
        plt.xlabel("classe predita")
        plt.ylabel("classe real")
        plt.tight_layout()
        plt.savefig(output_png, dpi=200)
        plt.close()
    except ImportError:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 6))
        image = ax.imshow(matrix_df.values, cmap="Blues")

        ax.set_xticks(range(len(matrix_df.columns)))
        ax.set_yticks(range(len(matrix_df.index)))
        ax.set_xticklabels(matrix_df.columns, rotation=45, ha="right")
        ax.set_yticklabels(matrix_df.index)

        for row in range(matrix_df.shape[0]):
            for col in range(matrix_df.shape[1]):
                ax.text(col, row, str(matrix_df.iloc[row, col]), ha="center", va="center", color="black")

        ax.set_title(title)
        ax.set_xlabel("classe predita")
        ax.set_ylabel("classe real")
        fig.colorbar(image)
        fig.tight_layout()
        fig.savefig(output_png, dpi=200)
        plt.close(fig)


def gerar_relatorio_validacao_ana(
    caminho_modelo_csv: str,
    caminho_ana_csv: str,
    diretorio_saida: str = "reports",
    col_data_modelo: str = "Data",
    col_risco: str = "Indice_Risco",
    col_data_ana: str = "Data",
    col_classe_ana: str = "Classe_ANA",
) -> dict:
    output_dir = Path(diretorio_saida)
    output_dir.mkdir(parents=True, exist_ok=True)

    df_modelo = pd.read_csv(caminho_modelo_csv)
    df_ana = pd.read_csv(caminho_ana_csv)

    resultado = validar_modelo_vs_ana(
        df_modelo=df_modelo,
        df_ana=df_ana,
        col_data_modelo=col_data_modelo,
        col_risco=col_risco,
        col_data_ana=col_data_ana,
        col_classe_ana=col_classe_ana,
    )

    matriz_path = output_dir / "relatorio_matriz_confusao_ana.csv"
    comparativo_path = output_dir / "relatorio_comparativo_modelo_ana.csv"
    metricas_path = output_dir / "relatorio_metricas_ana.csv"
    imagem_path = output_dir / "matriz_confusao_ana.png"

    matrix_df = resultado["matriz_confusao"]
    comparativo_df = resultado["comparativo"]

    if isinstance(matrix_df, pd.DataFrame) and not matrix_df.empty:
        matrix_df.to_csv(matriz_path, index=True)
        _save_confusion_png(matrix_df, imagem_path, "matriz de confusao - modelo vs ana")
    else:
        pd.DataFrame().to_csv(matriz_path, index=False)

    if isinstance(comparativo_df, pd.DataFrame):
        comparativo_df.to_csv(comparativo_path, index=False)

    metricas_df = pd.DataFrame(
        [
            {
                "n_amostras": resultado.get("n_amostras"),
                "kappa_ponderado": resultado.get("kappa_ponderado"),
                "acuracia": resultado.get("acuracia"),
            }
        ]
    )
    metricas_df.to_csv(metricas_path, index=False)

    return {
        "metricas": metricas_df,
        "matriz_confusao": matrix_df,
        "comparativo": comparativo_df,
        "arquivos": {
            "metricas_csv": str(metricas_path),
            "matriz_csv": str(matriz_path),
            "comparativo_csv": str(comparativo_path),
            "matriz_png": str(imagem_path),
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="gera relatorio de validacao do indice de risco contra classes da ana"
    )
    parser.add_argument("--modelo", required=True, help="caminho do csv do modelo")
    parser.add_argument("--ana", required=True, help="caminho do csv de ground truth da ana")
    parser.add_argument("--outdir", default="reports", help="diretorio de saida dos relatorios")
    parser.add_argument("--col-data-modelo", default="Data", help="nome da coluna de data no csv do modelo")
    parser.add_argument("--col-risco", default="Indice_Risco", help="nome da coluna do indice de risco")
    parser.add_argument("--col-data-ana", default="Data", help="nome da coluna de data no csv da ana")
    parser.add_argument("--col-classe-ana", default="Classe_ANA", help="nome da coluna da classe ana")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    resultado = gerar_relatorio_validacao_ana(
        caminho_modelo_csv=args.modelo,
        caminho_ana_csv=args.ana,
        diretorio_saida=args.outdir,
        col_data_modelo=args.col_data_modelo,
        col_risco=args.col_risco,
        col_data_ana=args.col_data_ana,
        col_classe_ana=args.col_classe_ana,
    )

    metricas = resultado["metricas"].iloc[0].to_dict()
    print("relatorio gerado com sucesso")
    print(f"amostras: {metricas.get('n_amostras')}")
    print(f"kappa ponderado: {metricas.get('kappa_ponderado')}")
    print(f"acuracia: {metricas.get('acuracia')}")

    arquivos = resultado["arquivos"]
    print("arquivos exportados:")
    print(f"- metricas: {arquivos['metricas_csv']}")
    print(f"- matriz csv: {arquivos['matriz_csv']}")
    print(f"- comparativo csv: {arquivos['comparativo_csv']}")
    print(f"- matriz png: {arquivos['matriz_png']}")


if __name__ == "__main__":
    main()
