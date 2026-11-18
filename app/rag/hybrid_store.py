import uuid
from functools import lru_cache
from typing import Optional
from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient, models
from app.core.config import get_settings
from app.schemas.audit import PolicyCitation

DENSE_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
SPARSE_MODEL_NAME = "Qdrant/bm25"
DENSE_VECTOR_SIZE = 384


class HybridPolicyStore:
    def __init__(self) -> None:
        settings = get_settings()
        self.collection_name = settings.qdrant_collection_name
        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=30,
        )
        self.dense_model = TextEmbedding(model_name=DENSE_MODEL_NAME)
        self.sparse_model = SparseTextEmbedding(model_name=SPARSE_MODEL_NAME)

    def ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection_name):
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                "dense": models.VectorParams(
                    size=DENSE_VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(
                    index=models.SparseIndexParams(on_disk=False)
                )
            },
        )

        # Payload index agar filter kategori berjalan cepat
        self.client.create_payload_index(
            collection_name=self.collection_name,
            field_name="category",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

    def upsert_policies(self, policies: list[dict]) -> int:
        """
        Setiap dict wajib memiliki: rule_code, category, section, content
        """
        self.ensure_collection()

        passages = [
            f"[{p['rule_code']}] {p['category']} - {p['section']}: {p['content']}"
            for p in policies
        ]
        raw_texts = [
            f"{p['rule_code']} {p['category']} {p['section']} {p['content']}"
            for p in policies
        ]

        dense_embeddings = list(self.dense_model.embed(passages))
        sparse_embeddings = list(self.sparse_model.embed(raw_texts))

        points: list[models.PointStruct] = []
        for policy, dense_vec, sparse_vec in zip(
            policies, dense_embeddings, sparse_embeddings
        ):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, policy["rule_code"]))
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector={
                        "dense": dense_vec.tolist(),
                        "sparse": models.SparseVector(
                            indices=sparse_vec.indices.tolist(),
                            values=sparse_vec.values.tolist(),
                        ),
                    },
                    payload={
                        "rule_code": policy["rule_code"],
                        "category": policy["category"],
                        "section": policy["section"],
                        "content": policy["content"],
                    },
                )
            )

        self.client.upsert(collection_name=self.collection_name, points=points)
        return len(points)

    def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        category_filter: Optional[str] = None,
    ) -> list[PolicyCitation]:
        self.ensure_collection()

        dense_query = next(self.dense_model.embed([query])).tolist()
        sparse_raw = next(self.sparse_model.embed([query]))
        sparse_query = models.SparseVector(
            indices=sparse_raw.indices.tolist(),
            values=sparse_raw.values.tolist(),
        )

        query_filter = None
        if category_filter and category_filter.lower() != "all":
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="category",
                        match=models.MatchValue(value=category_filter),
                    )
                ]
            )

        response = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                models.Prefetch(
                    query=dense_query,
                    using="dense",
                    filter=query_filter,
                    limit=top_k * 2,
                ),
                models.Prefetch(
                    query=sparse_query,
                    using="sparse",
                    filter=query_filter,
                    limit=top_k * 2,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )

        citations: list[PolicyCitation] = []
        for hit in response.points:
            payload = hit.payload or {}
            citations.append(
                PolicyCitation(
                    rule_code=payload.get("rule_code", "UNKNOWN"),
                    category=payload.get("category", "General"),
                    section=payload.get("section", "General"),
                    content=payload.get("content", ""),
                    relevance_score=round(float(hit.score), 4),
                )
            )

        return citations


@lru_cache
def get_policy_store() -> HybridPolicyStore:
    return HybridPolicyStore()
