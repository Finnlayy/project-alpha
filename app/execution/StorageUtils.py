"""
=========================================================
Datei:      app/execution/StorageUtils.py (v1.7.0)
Zweck:      Atomare E/A-Operationen, Parquet & Data Lake Writer
Knoten:     Jaune (Carrera-Engine) / Storage Layer
System:     "The Judge & The Swarm" - Zero-Dummy Guarantee
=========================================================
"""
from __future__ import annotations
import os
import tempfile
import logging
from typing import Any

logger = logging.getLogger("app.execution.storage_utils")


def write_parquet_atomically(target_path: str, table: Any) -> None:
    """
    Schreibt Tabellendaten (z.B. pyarrow.Table oder DataFrame) atomar auf das Dateisystem.
    Verhindert korrupte Dateien bei plötzlichem Abbruch durch Schreiben in eine temporäre
    Datei mit anschließendem atomarem OS-Rename (POSIX atomic swap).
    """
    target_dir = os.path.dirname(os.path.abspath(target_path))
    os.makedirs(target_dir, exist_ok=True)
    
    tmp_path = f"{target_path}.tmp"
    
    try:
        # Wenn pyarrow installiert ist, nutze pyarrow.parquet.write_table
        try:
            import pyarrow.parquet as pq
            pq.write_table(table, tmp_path)
        except ImportError:
            # Robuster Fallback ohne pyarrow
            import pickle
            with open(tmp_path, "wb") as f:
                pickle.dump(table, f)
        
        # Atomares Ersetzen der Zieldatei
        os.replace(tmp_path, target_path)
        logger.info("Atomar geschrieben: %s", target_path)
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        logger.error("Fehler beim atomaren Schreiben von %s: %s", target_path, e)
        raise e
