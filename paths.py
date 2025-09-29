"""Centralización de rutas de almacenamiento.

Evita repetir os.path.join(...) disperso. Si cambia la estructura, se ajusta aquí.
"""
from __future__ import annotations
import os
from functools import lru_cache

# Raíz del repositorio: este archivo vive en la raíz, por lo que dirname(__file__) es la raíz.
REPO_ROOT = os.path.abspath(os.path.dirname(__file__))

DATA_DIR = os.path.join(REPO_ROOT, 'data')
STORAGE_DIR = os.path.join(DATA_DIR, 'storage')
IMAGES_DIR = os.path.join(STORAGE_DIR, 'images')
GRAPH_SESSION_DIR = os.path.join(STORAGE_DIR, 'graph_session')

PUBLIC_IMAGES_PREFIX_PRIMARY = '/../data/storage/images'
PUBLIC_IMAGES_PREFIX_COMPAT = '/storage/images'

PUBLIC_GRAPH_SESSION_PREFIX = '/../data/storage/graph_session'

ALL_DIRS = [STORAGE_DIR, IMAGES_DIR, GRAPH_SESSION_DIR]
for d in ALL_DIRS:
    os.makedirs(d, exist_ok=True)

@lru_cache(maxsize=None)
def ensure_dirs() -> None:
    for d in ALL_DIRS:
        os.makedirs(d, exist_ok=True)

__all__ = [
    'REPO_ROOT', 'DATA_DIR', 'STORAGE_DIR', 'IMAGES_DIR', 'GRAPH_SESSION_DIR',
    'PUBLIC_IMAGES_PREFIX_PRIMARY', 'PUBLIC_IMAGES_PREFIX_COMPAT', 'PUBLIC_GRAPH_SESSION_PREFIX',
    'ensure_dirs'
]
