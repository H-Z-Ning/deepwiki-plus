#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1. 读取 JSON 文本 → 分块 → Embedding → 本地 FAISS 向量库
2. 根据 query 做语义检索
配置完全兼容 api/config/embedder.json
"""
import os
import json
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Optional

import openai
import ollama
import faiss
import numpy as np
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document as LcDocument

# ---------- 配置 ----------
CONFIG_DIR = os.environ.get('DEEPWIKI_CONFIG_DIR', None)
if CONFIG_DIR:
    CONFIG_PATH = Path(CONFIG_DIR) / "embedder.json"
else:
    # Otherwise use default directory
    CONFIG_PATH = Path(__file__).parent.parent/ "config" / "embedder.json"

with open(CONFIG_PATH, encoding="utf8") as f:
    CFG = json.load(f)

EMBED_CFG      = CFG["embedder"]          # OpenAI 配置
EMBED_OLLAMA_CFG = CFG.get("embedder_ollama")
RETRIEVER_CFG  = CFG["retriever"]
SPLIT_CFG      = CFG["text_splitter"]

# 环境变量替换
for k, v in EMBED_CFG["initialize_kwargs"].items():
    if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
        EMBED_CFG["initialize_kwargs"][k] = os.getenv(v[2:-1], "")

# ---------- 1. Embedding 客户端 ----------
class BaseEmbedder:
    """统一接口：list[str] -> np.ndarray"""
    def embed_documents(self, texts: List[str]) -> np.ndarray:
        raise NotImplementedError

class OpenAIEmbedder(BaseEmbedder):
    def __init__(self, cfg: dict):
        self.client = openai.OpenAI(**cfg["initialize_kwargs"])
        self.batch = cfg["batch_size"]
        self.model_kwargs = cfg["model_kwargs"]

    def embed_documents(self, texts: List[str]) -> np.ndarray:
        vecs = []
        for i in range(0, len(texts), self.batch):
            resp = self.client.embeddings.create(
                input=texts[i:i+self.batch], **self.model_kwargs
            )
            vecs += [d.embedding for d in resp.data]
        return np.array(vecs, dtype="float32")

class OllamaEmbedder(BaseEmbedder):
    def __init__(self, cfg: dict):
        self.model = cfg["model_kwargs"]["model"]

    def embed_documents(self, texts: List[str]) -> np.ndarray:
        vecs = [ollama.embeddings(model=self.model, prompt=t)["embedding"] for t in texts]
        return np.array(vecs, dtype="float32")

def get_embedder(use_ollama: bool = False) -> BaseEmbedder:
    if use_ollama:
        return OllamaEmbedder(EMBED_OLLAMA_CFG)
    return OpenAIEmbedder(EMBED_CFG)

# ---------- 2. 文本分块 ----------
def split_text(pages: List[str]) -> List[str]:
    splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""],
        chunk_size=SPLIT_CFG["chunk_size"],
        chunk_overlap=SPLIT_CFG["chunk_overlap"],
        length_function=len,
    )
    return splitter.split_text("\n\n".join(pages))

# ---------- 3. 向量库存储 / 加载 ----------
class LocalFAISSStore:
    """简单封装：保存 & 加载"""
    def __init__(self, index: faiss.IndexFlat, texts: List[str], metas: List[dict]):
        self.index = index
        self.texts = texts
        self.metas = metas

    def save(self, folder: str):
        os.makedirs(folder, exist_ok=True)
        faiss.write_index(self.index, os.path.join(folder, "index.bin"))
        with open(os.path.join(folder, "docs.json"), "w", encoding="utf8") as f:
            json.dump({"texts": self.texts, "metas": self.metas}, f, ensure_ascii=False)

    @staticmethod
    def load(folder: str) -> "LocalFAISSStore":
        index = faiss.read_index(os.path.join(folder, "index.bin"))
        with open(os.path.join(folder, "docs.json"), encoding="utf8") as f:
            d = json.load(f)
        return LocalFAISSStore(index, d["texts"], d["metas"])

# ---------- 4. 构建向量库 ----------
def build_vector_store(json_file: str, save_dir: str, use_ollama: bool = False):
    """读取单个 json，文本字段默认取 'text'"""
    print(f"[1] 读取原始文本 ...")
    with open(json_file, encoding="utf8") as f:
        data = json.load(f)
    # 如果 json 是 list[dict]，把每一项的 'text' 拼起来
    if isinstance(data, list):
        pages = [item.get("text", str(item)) for item in data]
    else:
        pages = [data.get("text", str(data))]

    print(f"[2] 分块 ...")
    chunks = split_text(pages)
    print(f"   共 {len(chunks)} 块")

    print(f"[3] 向量化 ...")
    embedder = get_embedder(use_ollama)
    vecs = embedder.embed_documents(chunks)
    d = vecs.shape[1]
    index = faiss.IndexFlatIP(d)   # 内积相似度（OpenAI 向量已归一化）
    faiss.normalize_L2(vecs)       # 必须归一化
    index.add(vecs)

    print(f"[4] 保存到 {save_dir}")
    store = LocalFAISSStore(index, chunks, [{} for _ in chunks])
    store.save(save_dir)
    return store

# ---------- 5. 语义检索 ----------
def semantic_search(query: str, store: LocalFAISSStore, top_k: int = 20):
    embedder = get_embedder(use_ollama=False)   # 检索默认用 OpenAI
    qvec = embedder.embed_documents([query])
    faiss.normalize_L2(qvec)
    D, I = store.index.search(qvec, top_k)
    results = []
    for score, idx in zip(D[0], I[0]):
        results.append({
            "score": float(score),
            "text" : store.texts[idx],
            "meta" : store.metas[idx]
        })
    return results






import os
import json
import textwrap
from typing import List, Dict
from pathlib import Path

# --------------- 前面所有函数不动 ---------------
# LocalFAISSStore / get_embedder / build_vector_store / semantic_search
# 把之前贴过的代码全部原样拷到此处即可，为避免篇幅省略重复部分
# ---------------------------------------------

def build_store(json_path: str,
                store_dir: str = "./faiss_store",
                use_ollama: bool = False) -> "LocalFAISSStore":
    """
    根据 json 文件建立向量库并返回 store 对象
    如目录已存在则直接加载返回，不再重复建库
    """
    store_dir = Path(store_dir)
    index_file = store_dir / "index.bin"
    if index_file.exists():
        print(f"[build_store] 向量库已存在，直接加载 {store_dir}")
        return LocalFAISSStore.load(str(store_dir))

    print(f"[build_store] 开始建库：{json_path} -> {store_dir}")
    store = build_vector_store(json_path, str(store_dir), use_ollama)
    return store


def similarity_search(json_path: str,
                      query: str,
                      store_dir: str = "./faiss_store",
                      top_k: int = None,
                      use_ollama: bool = False
                      ) -> List[Dict]:
    """
    语义检索入口，自动保证向量库存在
    返回 List[dict]，字段：score/text/meta
    """
    if top_k is None:
        top_k = RETRIEVER_CFG["top_k"]

    store_dir = Path(store_dir)
    index_file = store_dir / "index.bin"

    # 自动建库：默认用 OpenAI，如需 Ollama 请第一次手动调用 build_store
    if not index_file.exists():
        print(
            f"向量库 {store_dir} 不存在！正在调用 build_store(json_path, store_dir) 建库。"
        )
        build_store(json_path,store_dir,use_ollama)

    store = LocalFAISSStore.load(str(store_dir))
    return semantic_search(query, store, top_k)


# ---------------- 简易 CLI ----------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="JSON → FAISS 向量库 → 语义检索")
    parser.add_argument("--json", help="输入 json 文件（建库时用）")
    parser.add_argument("--store", default="./faiss_store", help="向量库目录")
    parser.add_argument("--ollama", action="store_true", help="用 ollama 建库")
    parser.add_argument("--query", help="检索语句")
    args = parser.parse_args()

    # 建库
    if args.json:
        build_store(args.json, args.store, args.ollama)

    # 检索
    if args.query:
        hits = similarity_search(args.query, args.store)
        print("\n===== 语义检索结果 =====")
        for rank, doc in enumerate(hits, 1):
            print(f"{rank}. score={doc['score']:.3f}")
            print(textwrap.fill(doc["text"], width=90))
            print("-" * 90)
