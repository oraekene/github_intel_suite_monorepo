"""
pia/test_setup.py

Quick sanity-check script. Run this BEFORE your first full pipeline run
to verify:
  1. Config is loaded without errors
  2. Knowledge base directory is reachable
  3. Embedding model can be loaded (CPU)
  4. ChromaDB can persist + query
  5. Anthropic API key is valid (sends a tiny test message)
  6. At least one local project path is reachable

Usage:
    python test_setup.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import load_config, cfg, log

PASS  = "✅"
FAIL  = "❌"
WARN  = "⚠️ "


def test_config() -> bool:
    try:
        cfg_data = load_config()
        log.info(f"{PASS} Config loaded OK")
        return True
    except Exception as e:
        log.error(f"{FAIL} Config error: {e}")
        return False


def test_knowledge_base_dir() -> bool:
    kb_dir = Path(cfg("knowledge_base.source_dir", ""))
    if not kb_dir.exists():
        log.error(f"{FAIL} Knowledge base dir not found: {kb_dir}")
        log.info("   → Update 'knowledge_base.source_dir' in config.yaml")
        return False

    files = list(kb_dir.rglob("*.md")) + list(kb_dir.rglob("*.txt"))
    if not files:
        log.warning(f"{WARN} Knowledge base dir exists but no .md/.txt files found: {kb_dir}")
        return True

    log.info(f"{PASS} Knowledge base dir OK — {len(files)} .md/.txt files found")
    return True


def test_embedding_model() -> bool:
    model_name = cfg("knowledge_base.embedding_model", "all-MiniLM-L6-v2")
    try:
        log.info(f"  Loading embedding model '{model_name}'…")
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name, device="cpu")
        vec   = model.encode(["hello world"])
        assert len(vec[0]) > 0
        log.info(f"{PASS} Embedding model loaded — vector dim: {len(vec[0])}")
        return True
    except Exception as e:
        log.error(f"{FAIL} Embedding model error: {e}")
        return False


def test_chromadb() -> bool:
    import tempfile
    try:
        import chromadb
        from chromadb.utils import embedding_functions

        with tempfile.TemporaryDirectory() as tmpdir:
            client = chromadb.PersistentClient(path=tmpdir)
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2", device="cpu"
            )
            col = client.get_or_create_collection("test", embedding_function=ef)
            col.upsert(
                ids=["t1"],
                documents=["ChromaDB test document for PIA"],
                metadatas=[{"test": True}],
            )
            results = col.query(query_texts=["test document"], n_results=1)
            assert results["ids"][0][0] == "t1"
        log.info(f"{PASS} ChromaDB — upsert + query OK")
        return True
    except Exception as e:
        log.error(f"{FAIL} ChromaDB error: {e}")
        return False


def test_anthropic_api() -> bool:
    api_key = cfg("anthropic.api_key", "")
    if not api_key or api_key.startswith("<REPLACE"):
        log.warning(f"{WARN} Anthropic API key not set — skipping API test")
        return True  # Not a hard failure — user might fill later

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp   = client.messages.create(
            model      = cfg("anthropic.model", "claude-sonnet-4-20250514"),
            max_tokens = 30,
            messages   = [{"role": "user", "content": "Reply with: PIA test OK"}],
        )
        reply = resp.content[0].text.strip()
        log.info(f"{PASS} Anthropic API — response: '{reply}'")
        return True
    except Exception as e:
        log.error(f"{FAIL} Anthropic API error: {e}")
        return False


def test_local_project_paths() -> bool:
    roots = cfg("projects.local.roots", [])
    if not roots:
        log.warning(f"{WARN} No local project roots configured")
        return True

    ok = True
    for root in roots:
        p = Path(root)
        if p.exists():
            count = sum(1 for _ in p.iterdir() if _.is_dir())
            log.info(f"{PASS} Local root: {root} ({count} sub-folders)")
        else:
            log.error(f"{FAIL} Local root not found: {root}")
            ok = False

    return ok


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 55)
    print("  PIA Setup Test")
    print("=" * 55 + "\n")

    tests = [
        ("Config",             test_config),
        ("Knowledge base dir", test_knowledge_base_dir),
        ("Embedding model",    test_embedding_model),
        ("ChromaDB",           test_chromadb),
        ("Anthropic API",      test_anthropic_api),
        ("Local project paths",test_local_project_paths),
    ]

    passed = 0
    failed = 0

    for name, fn in tests:
        print(f"  Testing: {name}…")
        try:
            ok = fn()
        except Exception as e:
            log.error(f"{FAIL} {name} raised exception: {e}")
            ok = False
        if ok:
            passed += 1
        else:
            failed += 1
        print()

    print("=" * 55)
    print(f"  Results: {passed} passed, {failed} failed")
    print("=" * 55 + "\n")

    if failed == 0:
        print("  🎉 All tests passed! You're ready to run:")
        print("     python scheduler/run_pipeline.py\n")
    else:
        print("  ⚠️  Fix the issues above before running the pipeline.\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()


# ── Test 7: New analysis modules ──────────────────────────────────────────────

def test_new_modules():
    print("\n[7] Testing new intent / comparison / constraint modules…")
    errors = []

    # Constraints builder
    try:
        from analysis.constraints import build_constraints_block
        block = build_constraints_block()
        # block can be empty string if config not filled — that's fine
        print(f"    constraints.build_constraints_block() → {len(block)} chars  ✓")
    except Exception as e:
        errors.append(f"constraints: {e}")

    # User prompts loader
    try:
        from analysis.user_prompts_loader import get_prompts_for_module
        p = get_prompts_for_module("code_review")
        print(f"    user_prompts_loader.get_prompts_for_module() → {len(p)} chars  ✓")
    except Exception as e:
        errors.append(f"user_prompts_loader: {e}")

    # Project profiler (import only — don't call API)
    try:
        from analysis.project_profiler import build_project_profile
        print("    project_profiler imported  ✓")
    except Exception as e:
        errors.append(f"project_profiler: {e}")

    # Intent analyzer (import only)
    try:
        from analysis.intent_analyzer import analyse_intent
        print("    intent_analyzer imported  ✓")
    except Exception as e:
        errors.append(f"intent_analyzer: {e}")

    # Comparator (import only)
    try:
        from analysis.comparator import compare_approaches
        print("    comparator imported  ✓")
    except Exception as e:
        errors.append(f"comparator: {e}")

    if errors:
        for err in errors:
            print(f"    ✗ {err}")
        return False

    print("  ✅ All new modules OK")
    return True


if __name__ == "__main__":
    # Re-run with new test appended
    import sys
    ok7 = test_new_modules()
    if not ok7:
        sys.exit(1)
