"""文本向量化服务 — sentence-transformers封装，支持本地模型/ModelScope/HuggingFace"""

from __future__ import annotations
import os
import logging
from pathlib import Path
import numpy as np

from app.utils.config import load_settings, get_data_dir

logger = logging.getLogger(__name__)

# 全局模型实例（懒加载）
_embedding_model = None
_CACHE_DIR = None


def _find_local_model(model_name: str, cache_dir: str) -> str | None:
    """在缓存目录中查找已下载的模型，返回本地路径或 None"""
    cache = Path(cache_dir)
    if not cache.exists():
        return None

    # 标准化模型名：BAAI/bge-large-zh-v1.5 → 多种命名变体
    org_part, model_part = model_name.split("/") if "/" in model_name else ("", model_name)
    candidates = [
        model_part,                                    # bge-large-zh-v1.5
        model_part.replace(".", "___"),                # bge-large-zh-v1___5 (ModelScope)
        model_part.replace(".", "-"),                  # bge-large-zh-v1-5
    ]

    # 搜索范围：cache_dir 下所有子目录（不限层级）
    for root, dirs, _ in os.walk(str(cache)):
        # 跳过临时目录
        dirs[:] = [d for d in dirs if d not in (".lock", "._____temp")]
        for d in dirs:
            full = Path(root) / d
            if (full / "pytorch_model.bin").exists() or (full / "model.safetensors").exists():
                return str(full)

    return None


def _download_from_modelscope(model_name: str, cache_dir: str) -> str:
    """从 ModelScope 下载模型，返回本地路径"""
    try:
        from modelscope import snapshot_download
        logger.info(f"从 ModelScope 下载模型: {model_name}")
        return snapshot_download(model_name, cache_dir=cache_dir)
    except ImportError:
        raise RuntimeError("modelscope 未安装，请执行: pip install modelscope")
    except Exception as e:
        raise RuntimeError(f"从 ModelScope 下载模型失败: {e}") from e


def _download_from_hf_mirror(model_name: str, cache_dir: str) -> str:
    """通过 HuggingFace 镜像显式下载模型"""
    from huggingface_hub import snapshot_download
    endpoint = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
    logger.info(f"使用 HuggingFace 镜像下载: {model_name} (endpoint={endpoint})")
    return snapshot_download(
        model_name,
        cache_dir=cache_dir,
        endpoint=endpoint,
        resume_download=True,
    )


def _load_model():
    """懒加载 Embedding 模型"""
    global _embedding_model, _CACHE_DIR

    if _embedding_model is not None:
        return _embedding_model

    settings = load_settings()
    emb_cfg = settings.get("embedding", {})
    model_name = emb_cfg.get("model_name", "BAAI/bge-large-zh-v1.5")
    device = emb_cfg.get("device", "cpu")
    cache_dir = emb_cfg.get("cache_dir", "./data/cache/models")

    # 设置 HuggingFace 镜像端点，避免直连 huggingface.co 导致 SSL 错误
    hf_endpoint = emb_cfg.get("hf_endpoint", "https://hf-mirror.com")
    if hf_endpoint and "HF_ENDPOINT" not in os.environ:
        os.environ["HF_ENDPOINT"] = hf_endpoint
        logger.info(f"设置 HuggingFace 镜像端点: {hf_endpoint}")

    # 解析为绝对路径
    cache_path = Path(cache_dir)
    if not cache_path.is_absolute():
        from app.utils.config import ROOT_DIR
        cache_path = ROOT_DIR / cache_dir
    cache_dir = str(cache_path)
    _CACHE_DIR = cache_dir

    model_path = None

    # 1. 优先使用配置指定的本地路径
    local_path = emb_cfg.get("local_model_path", "")
    if local_path and Path(local_path).exists():
        model_path = local_path
        logger.info(f"使用本地模型: {model_path}")

    # 2. 在缓存目录中搜索已下载的模型
    if not model_path:
        model_path = _find_local_model(model_name, cache_dir)

    # 3. 尝试 ModelScope 下载
    if not model_path:
        logger.info("本地缓存未找到模型，尝试从 ModelScope 下载...")
        try:
            model_path = _download_from_modelscope(model_name, cache_dir)
        except RuntimeError as e:
            logger.warning(f"ModelScope 下载失败: {e}")

    # 4. 回退到 HuggingFace 镜像（显式传 endpoint，不依赖环境变量）
    if not model_path:
        try:
            model_path = _download_from_hf_mirror(model_name, cache_dir)
        except ImportError:
            raise RuntimeError("huggingface_hub 未安装，请执行: pip install huggingface_hub")
        except Exception as e:
            raise RuntimeError(
                f"模型下载失败，所有渠道均已尝试。\n"
                f"请手动下载模型到 {cache_dir}:\n"
                f"  pip install modelscope && python -c \"from modelscope import snapshot_download; "
                f"snapshot_download('{model_name}', cache_dir='{cache_dir}')\"\n"
                f"原始错误: {e}"
            ) from e

    logger.info(f"加载 Embedding 模型: {model_name} → {model_path} (device={device})")

    try:
        from sentence_transformers import SentenceTransformer
        # 先尝试离线模式（本地缓存已存在时无需网络请求）
        try:
            _embedding_model = SentenceTransformer(
                model_path, cache_folder=cache_dir, local_files_only=True
            )
            logger.info("Embedding 模型加载完成（离线模式）")
        except Exception:
            _embedding_model = SentenceTransformer(
                model_path, cache_folder=cache_dir
            )
            logger.info("Embedding 模型加载完成（在线模式）")
        if device == "cuda":
            _embedding_model = _embedding_model.to("cuda")
        logger.info("Embedding 模型加载完成")
    except ImportError:
        raise RuntimeError("sentence-transformers 未安装，请执行: pip install sentence-transformers")
    except OSError as e:
        raise RuntimeError(
            f"模型加载失败: {e}\n"
            f"模型路径: {model_path}\n"
            f"请确保模型已下载到本地或网络可访问。"
        ) from e

    return _embedding_model


class EmbeddingService:
    """文本向量化服务"""

    def __init__(self, device: str | None = None):
        settings = load_settings()
        emb_cfg = settings.get("embedding", {})
        self.dimension = emb_cfg.get("dimension", 1024)
        self.batch_size = emb_cfg.get("batch_size", 8)
        self.model = _load_model()
        if device:
            self.model = self.model.to(device)

    def encode(self, texts: list[str]) -> np.ndarray:
        """将文本列表编码为向量（同步）"""
        if not texts:
            return np.array([])
        embeddings = self.model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return np.array(embeddings)

    def encode_single(self, text: str) -> np.ndarray:
        """单条文本编码"""
        return self.encode([text])[0]

    def encode_queries(self, queries: list[str]) -> np.ndarray:
        """查询文本编码（使用query前缀）"""
        if not queries:
            return np.array([])
        prefixed = [f"为这个句子生成表示以用于检索相关文章：{q}" for q in queries]
        return self.encode(prefixed)

    def encode_query(self, query: str) -> np.ndarray:
        """单条查询编码"""
        return self.encode_queries([query])[0]

    def similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算两个向量的余弦相似度（已归一化时等于点积）"""
        return float(np.dot(vec1, vec2))

    def batch_similarity(self, query_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
        """批量计算查询向量与文档向量的相似度"""
        return np.dot(doc_vecs, query_vec)

    def is_available(self) -> bool:
        return self.model is not None
