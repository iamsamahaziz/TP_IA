import requests
import time
import os
from retry import retry

# 🔐 clé depuis variable d'environnement
MISTRAL_KEY = os.getenv("MISTRAL_KEY") or os.getenv("MISTRAL_API_KEY")

# 🌐 Qdrant (accessible depuis Jenkins Docker)
QDRANT_URL = os.getenv("QDRANT_URL", "http://host.docker.internal:6333")

DOCS_DIR = "documents"


# =========================
# 🔐 HEALTH CHECK MISTRAL
# =========================
def check_mistral_key():
    if not MISTRAL_KEY:
        raise ValueError("❌ MISTRAL_KEY est manquante dans les variables d'environnement")

    print("🔐 Vérification de la clé Mistral...")

    resp = requests.get(
        "https://api.mistral.ai/v1/models",
        headers={"Authorization": f"Bearer {MISTRAL_KEY}"}
    )

    if resp.status_code == 401:
        raise ValueError("❌ Clé Mistral invalide (401 Unauthorized)")

    if resp.status_code != 200:
        raise ValueError(f"❌ Erreur API Mistral: {resp.text}")

    print("✅ Clé Mistral valide")


# =========================
# 📂 LOAD DOCUMENTS
# =========================
def load_real_documents():
    documents_found = []

    if not os.path.exists(DOCS_DIR):
        print(f"❌ Erreur : Le dossier {DOCS_DIR} n'existe pas.")
        return []

    files = [f for f in os.listdir(DOCS_DIR) if f.endswith(".txt")]

    for filename in files:
        filepath = os.path.join(DOCS_DIR, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    documents_found.append({
                        "type": filename.replace(".txt", ""),
                        "content": content
                    })
        except Exception as e:
            print(f"⚠️ Impossible de lire {filename}: {e}")

    return documents_found


# =========================
# 🧠 QDRANT COLLECTION
# =========================
def ensure_collection():
    print(f"📡 Vérification de la collection 'AdminBot' sur {QDRANT_URL}...")

    try:
        check_resp = requests.get(f"{QDRANT_URL}/collections/AdminBot")

        if check_resp.status_code == 404:
            print("📦 Création de la collection 'AdminBot'...")

            create_resp = requests.put(
                f"{QDRANT_URL}/collections/AdminBot",
                json={
                    "vectors": {
                        "size": 1024,
                        "distance": "Cosine"
                    }
                }
            )

            if create_resp.status_code in [200, 201]:
                print("✅ Collection créée")
            else:
                print(f"❌ Erreur création: {create_resp.text}")

        else:
            print("✅ Collection déjà existante")

    except Exception as e:
        print(f"⚠️ Erreur Qdrant: {e}")


# =========================
# 🚀 START PIPELINE
# =========================

# 🔐 IMPORTANT : health check AVANT tout
check_mistral_key()

# 📂 load docs
docs = load_real_documents()
print(f"📚 {len(docs)} documents chargés")

# 🧠 Qdrant setup
ensure_collection()


# =========================
# 🔁 EMBEDDING BATCH PIPELINE
# =========================
if docs:
    print("🧠 Génération des embeddings par lots (Batching)...")
    inputs = [doc["content"] for doc in docs]

    @retry(tries=3, delay=2, backoff=2)
    def call_mistral_batch(text_list):
        resp = requests.post(
            "https://api.mistral.ai/v1/embeddings",
            headers={"Authorization": f"Bearer {MISTRAL_KEY}"},
            json={
                "model": "mistral-embed",
                "input": text_list
            }
        )

        if resp.status_code == 429:
            raise Exception("Rate limit exceeded")

        return resp

    try:
        resp = call_mistral_batch(inputs)
        if resp.status_code == 200:
            embeddings_data = resp.json()["data"]
            points = []
            
            for i, doc in enumerate(docs):
                emb = embeddings_data[i]["embedding"]
                points.append({
                    "id": i + 1,
                    "vector": emb,
                    "payload": {
                        "content": doc["content"],
                        "type": doc["type"]
                    }
                })
            
            print(f"📡 Envoi de {len(points)} points vers Qdrant...")
            qdrant_resp = requests.put(
                f"{QDRANT_URL}/collections/AdminBot/points",
                json={"points": points}
            )

            if qdrant_resp.status_code in [200, 201]:
                print(f"✅ {len(points)} documents indexés avec succès dans Qdrant !")
            else:
                print(f"❌ Qdrant error: {qdrant_resp.text}")
        else:
            print(f"❌ Erreur Mistral API: {resp.text}")
    except Exception as e:
        print(f"❌ Erreur lors du traitement par lots : {e}")

print("🎉 Pipeline terminé avec succès !")
