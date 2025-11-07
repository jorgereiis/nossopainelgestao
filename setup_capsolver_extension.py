#!/usr/bin/env python3
"""
Script de instalação e configuração automática da CapSolver Extension.

Etapas:
1. Baixa a extensão oficial do GitHub (branch main).
2. Extrai para cadastros/services/capsolver_extension/ (padrão).
3. Injeta CAPSOLVER_API_KEY no config.js/configuration.js quando encontrado.

Uso:
    python setup_capsolver_extension.py \
        --target-dir cadastros/services/capsolver_extension \
        --api-key SUA_CAPSOLVER_KEY

Se --api-key não for informado, o script tenta ler a variável
de ambiente CAPSOLVER_API_KEY (carregada do .env).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
from urllib.request import urlopen

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


DEFAULT_ZIP_URLS = [
    "https://github.com/capsolver/capsolver-browser-extension/releases/latest/download/capsolver-browser-extension.zip",
    "https://github.com/capsolver/capsolver-browser-extension/raw/main/capsolver-browser-extension.zip",
    "https://github.com/capsolver/capsolver-browser-extension/archive/refs/heads/main.zip",
]
DEFAULT_TARGET = Path("cadastros/services/capsolver_extension")


def read_api_key(cli_key: Optional[str]) -> str:
    """Resolve API key via CLI ou .env."""
    if cli_key:
        return cli_key.strip()
    if load_dotenv:
        load_dotenv()
    api_key = os.getenv("CAPSOLVER_API_KEY")
    if not api_key:
        print("❌ CAPSOLVER_API_KEY não encontrada. Use --api-key ou defina no .env.", file=sys.stderr)
        sys.exit(1)
    return api_key.strip()


def download_extension_zip(urls: list[str]) -> Path:
    """Baixa o zip tentando múltiplos links até obter sucesso."""
    last_error: Optional[Exception] = None
    for url in urls:
        try:
            print(f"⬇️  Baixando CapSolver Extension de {url} ...")
            with urlopen(url) as response:  # nosec - URL controlada
                data = response.read()
            tmp_file = Path(tempfile.mkstemp(suffix=".zip")[1])
            tmp_file.write_bytes(data)
            return tmp_file
        except Exception as exc:  # pragma: no cover
            last_error = exc
            print(f"⚠️  Falha ao baixar de {url}: {exc}")

    raise SystemExit(
        "Não foi possível baixar automaticamente. "
        "Informe manualmente com --zip-url <URL> ou baixe o zip e extraia no diretório alvo."
    ) from last_error


def extract_zip(zip_path: Path, target_dir: Path) -> None:
    """Extrai zip para target_dir (substitui conteúdo atual)."""
    if target_dir.exists():
        print(f"🧹 Removendo diretório existente: {target_dir}")
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        top_level = zf.namelist()[0].split("/")[0]
        zf.extractall(target_dir.parent)
    extracted_root = target_dir.parent / top_level
    print(f"📦 Copiando arquivos para {target_dir}")
    shutil.move(str(extracted_root), str(target_dir))


def inject_api_key(target_dir: Path, api_key: str) -> None:
    """Procura arquivos config.js/configuration.js e injeta API key."""
    candidates = []
    for file in target_dir.rglob("config*.js"):
        candidates.append(file)

    if not candidates:
        # cria config.js básico
        config_file = target_dir / "config.js"
        config_file.write_text(f"window.capSolverConfig = {{ apiKey: '{api_key}' }};\n")
        print(f"⚠️ config.js não encontrado; criado {config_file}")
        return

    for config_file in candidates:
        text = config_file.read_text(encoding="utf-8")
        if "apiKey" in text:
            new_text = []
            replaced = False
            for line in text.splitlines():
                if "apiKey" in line and ":" in line:
                    new_text.append(f"    apiKey: '{api_key}',")
                    replaced = True
                else:
                    new_text.append(line)
            if replaced:
                config_file.write_text("\n".join(new_text), encoding="utf-8")
                print(f"✅ API key atualizada em {config_file}")
                return

    # fallback: sobrescreve primeiro arquivo
    config_file = candidates[0]
    config_file.write_text(f"window.capSolverConfig = {{ apiKey: '{api_key}' }};\n", encoding="utf-8")
    print(f"⚠️ Estrutura desconhecida. Substituído {config_file} com configuração simples.")


def main():
    parser = argparse.ArgumentParser(description="Setup automático da CapSolver Extension.")
    parser.add_argument("--target-dir", default=str(DEFAULT_TARGET), help="Diretório de destino da extensão.")
    parser.add_argument(
        "--zip-url",
        help="URL do zip oficial da extensão. Quando omitido, tenta URLs padrão da CapSolver.",
    )
    parser.add_argument("--api-key", help="CAPSOLVER_API_KEY para gravar no config.js.")
    args = parser.parse_args()

    api_key = read_api_key(args.api_key)
    target_dir = Path(args.target_dir).resolve()

    urls = [args.zip_url] if args.zip_url else DEFAULT_ZIP_URLS
    zip_path = download_extension_zip(urls)
    try:
        extract_zip(zip_path, target_dir)
    finally:
        zip_path.unlink(missing_ok=True)

    inject_api_key(target_dir, api_key)

    print("\n✅ CapSolver Extension instalada com sucesso!")
    print(f"   Diretório: {target_dir}")
    print("   Configure no .env:")
    print(f"      CAPSOLVER_EXTENSION_PATH='{target_dir}'")
    print("   Em seguida, use CAPSOLVER_METHOD=auto ou CAPSOLVER_METHOD=extension.")


if __name__ == "__main__":
    main()
