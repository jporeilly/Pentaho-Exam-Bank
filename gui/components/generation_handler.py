"""Generation handler: on_generate, on_generate_batch, auto-QA, duplicate replacement.

Extracted from web_app.py to keep the main app file focused on layout and wiring.
"""

import threading
import time

from nicegui import ui

from ..state import AppState, UIRefs, EVT_ACTION_BAR_CHANGED, EVT_QUESTIONS_CHANGED
from ...core.question_generator import generate_questions_batch, qa_check_question, qa_fix_question
from ...core import mcp_client
from ...utils.config import config


def _stem_similar_to_any(stem, existing_stems, threshold=0.85):
    """Check if stem is similar to any in a list using word overlap."""
    if not stem:
        return False
    norm = " ".join(stem.lower().split())
    words = set(norm.split())
    if not words:
        return False
    for ex in existing_stems:
        ex_norm = " ".join((ex or "").lower().split())
        if not ex_norm:
            continue
        if norm == ex_norm:
            return True
        ex_words = set(ex_norm.split())
        overlap = len(words & ex_words) / max(len(words), len(ex_words))
        if overlap >= threshold:
            return True
    return False


def auto_qa_batch(state, refs, _callback_anchor):
    """Run QA check on all generated questions that don't already have QA tags."""
    questions_to_qa = [
        (i, q) for i, q in enumerate(state.generated_questions)
        if not any(t.startswith("qa:") for t in q.tags)
    ]
    if not questions_to_qa:
        return

    ui.notify(f"Running auto-QA on {len(questions_to_qa)} question(s)...", type="info")

    def do_qa():
        results = {}
        for i, q in questions_to_qa:
            try:
                issues = qa_check_question(
                    question=q, model=config.ollama_model,
                    base_url=config.ollama_url,
                )
                results[i] = issues or []
            except Exception:
                results[i] = []
        return results

    def on_qa_done(results):
        needs_fix = {}
        passed = 0
        for i, issues in results.items():
            if i >= len(state.generated_questions):
                continue
            q = state.generated_questions[i]
            q.tags = [t for t in q.tags if not t.startswith("qa:")]
            if issues:
                needs_fix[i] = issues
            else:
                passed += 1
        if needs_fix:
            ui.notify(
                f"Auto-QA: {passed} passed, {len(needs_fix)} need fixing — auto-fixing...",
                type="warning",
            )
            _auto_fix_batch(state, needs_fix, _callback_anchor)
        else:
            ui.notify("Auto-QA: all questions passed", type="positive")
            state.bus.emit(EVT_QUESTIONS_CHANGED)

    def run_qa():
        result = do_qa()
        with _callback_anchor:
            ui.timer(0, lambda: (on_qa_done(result), False), once=True)

    thread = threading.Thread(target=run_qa, daemon=True)
    thread.start()


def _auto_fix_batch(state, fix_map, _callback_anchor, attempt=1, max_attempts=3):
    """Fix all questions with issues, then re-QA. Loop up to max_attempts."""
    def do_fixes():
        results = {}
        for idx, issues in fix_map.items():
            if idx >= len(state.generated_questions):
                continue
            q = state.generated_questions[idx]
            try:
                fixed = qa_fix_question(
                    question=q, issues=issues,
                    model=config.ollama_model, base_url=config.ollama_url,
                    system_prompt=config.system_prompt,
                )
                if fixed:
                    state.generated_questions[idx] = fixed
                    new_issues = qa_check_question(
                        question=fixed, model=config.ollama_model,
                        base_url=config.ollama_url,
                    )
                    results[idx] = new_issues or []
                else:
                    results[idx] = issues
            except Exception:
                results[idx] = issues
        return results

    def on_fixes_done(results):
        still_broken = {}
        for idx, issues in results.items():
            if idx >= len(state.generated_questions):
                continue
            q = state.generated_questions[idx]
            q.tags = [t for t in q.tags if not t.startswith("qa:")]
            if issues:
                still_broken[idx] = issues

        if not still_broken:
            ui.notify(f"All questions fixed after {attempt} attempt(s)", type="positive")
            state.bus.emit(EVT_QUESTIONS_CHANGED)
        elif attempt < max_attempts:
            ui.notify(
                f"{len(still_broken)} question(s) still have issues — retry {attempt + 1}/{max_attempts}...",
                type="info",
            )
            _auto_fix_batch(state, still_broken, _callback_anchor, attempt + 1, max_attempts)
        else:
            for idx, issues in still_broken.items():
                if idx < len(state.generated_questions):
                    q = state.generated_questions[idx]
                    for issue in issues:
                        tag = f"qa:{issue.get('severity', 'warning')}:{issue.get('field', 'general')}:{issue['issue']}"
                        q.tags.append(tag)
            ui.notify(
                f"Auto-fix done ({max_attempts} attempts) — {len(still_broken)} question(s) still have issues",
                type="warning",
            )
            state.bus.emit(EVT_QUESTIONS_CHANGED)

    def run_fixes():
        result = do_fixes()
        with _callback_anchor:
            ui.timer(0, lambda: (on_fixes_done(result), False), once=True)

    threading.Thread(target=run_fixes, daemon=True).start()


def setup_generation_handlers(state: AppState, refs: UIRefs, _callback_anchor):
    """Wire up on_generate and on_generate_batch onto refs. Call once from create_app."""

    def on_generate():
        """Trigger question generation for the current slide or docs."""
        if state.is_generating:
            return
        if not config.ollama_enabled:
            ui.notify("Ollama is disabled — enable it in AI & Docs", type="warning")
            return
        if not config.ollama_model:
            ui.notify("No Ollama model selected — check AI & Docs", type="warning")
            return

        f = state.selected_file
        cert_id = (f.certification_id if f else "") or state.active_cert_id
        if not cert_id:
            ui.notify("Select a certification first (sidebar)", type="warning")
            return
        cert = state.db.get_certification(cert_id)
        is_docs = bool(cert and cert.source_type == "docs")
        is_pcm = bool(cert and cert.source_type == "pcm")

        if is_docs:
            file_topic = state.active_topic or (f.topic if f else "") or (cert.name if cert else "")
            if not file_topic:
                ui.notify("Set a topic (sidebar) to search documentation", type="warning")
                return
            if not config.mcp_enabled or not config.mcp_servers:
                ui.notify("MCP documentation servers not configured — check AI & Docs", type="warning")
                return
            if state.active_mcp_servers is not None and len(state.active_mcp_servers) == 0:
                ui.notify("Select at least one MCP server in the sidebar", type="warning")
                return
        elif is_pcm:
            if not config.pcm_courses_dir:
                ui.notify("Set the PCM courses directory in Settings", type="warning")
                return
            if not cert.source_ref:
                ui.notify("Pick a PCM course first (sidebar)", type="warning")
                return
        else:
            if not f or not f.reader:
                ui.notify("No file loaded — add a PPTX first", type="warning")
                return

        if not is_docs and not is_pcm:
            slide = state.current_slide
            slide_idx = state.current_slide_idx
            if not slide:
                ui.notify("No slide selected", type="warning")
                return
            if not slide.speaker_notes.strip() and not slide.body_text:
                ui.notify(f"Slide {slide_idx + 1} has no content to generate from", type="warning")
                return

        if refs.tabs and refs.generate_tab:
            refs.tabs.set_value(refs.generate_tab)

        state.is_generating = True
        state._cancel_generation = False
        state.progress_fraction = 0
        state._gen_start_time = time.time()

        difficulty = config.default_difficulty
        bloom = config.default_bloom_level
        if not is_docs and not is_pcm:
            file_topic = (f.topic if f else "") or ""
        include_scenario = getattr(state, '_gen_include_scenario', True)

        ui_specs = getattr(state, '_gen_question_specs', [{"keys": 1, "distractors": 3}])
        question_specs = _build_question_specs(ui_specs)
        num_per = len(question_specs)

        custom = ""
        if not include_scenario:
            custom = "Do NOT include a scenario. Leave the 'scenario' field as an empty string."
        if config.mermaid_enabled:
            custom += (
                "\n\nIn the 'explanation' field, when describing processes, workflows, or relationships, "
                "include a Mermaid diagram using a ```mermaid code fence. Use flowchart, sequence, "
                "state, or mindmap syntax as appropriate. Keep diagrams concise."
            )

        if is_docs:
            state.progress_message = f"Searching docs for '{file_topic or cert.name}' — generating {num_per} question(s)..."
        elif is_pcm:
            state.progress_message = f"Reading PCM course '{cert.source_ref}' — generating questions..."
        else:
            slide_idx = state.current_slide_idx
            state.progress_message = f"Slide {slide_idx + 1} — generating {num_per} question(s)..."

        def do_generate():
            def progress_cb(current, total, message):
                if state._cancel_generation:
                    raise InterruptedError("Generation cancelled by user")
                state.progress_fraction = current / total if total else 0
                state.progress_message = message

            if is_docs:
                return _generate_from_docs(
                    state, cert_id, cert, file_topic, num_per, difficulty, bloom,
                    custom, question_specs, progress_cb,
                )
            elif is_pcm:
                return _generate_from_pcm(
                    state, cert_id, cert, num_per, difficulty, bloom,
                    custom, question_specs, progress_cb,
                )
            else:
                slide = state.current_slide
                slide_idx = state.current_slide_idx
                img = f.slide_images[slide_idx] if slide_idx < len(f.slide_images) else None
                slide_image_paths = [str(img) if img and img.exists() else None]
                return generate_questions_batch(
                    slides=[slide],
                    model=config.ollama_model,
                    base_url=config.ollama_url,
                    num_per_slide=num_per,
                    difficulty=difficulty,
                    bloom_level=bloom,
                    certification_id=cert_id,
                    source_file=f.path.name,
                    system_prompt=config.system_prompt,
                    progress_callback=progress_cb,
                    topic=file_topic,
                    custom_instructions=custom,
                    slide_images=slide_image_paths,
                    question_specs=question_specs,
                )

        # Progress polling timer
        with _callback_anchor:
            timer = ui.timer(0.8, lambda: _poll_progress(state))

        def run_and_finish():
            raw_questions = []
            error_msg = ""
            cancelled = False
            try:
                label = f"docs:{file_topic}" if is_docs else f"slide {slide_idx + 1}"
                print(f"[GENERATE] Starting for {label}...")
                raw_questions = do_generate()
                print(f"[GENERATE] Got {len(raw_questions)} question(s) from AI")
            except InterruptedError:
                cancelled = True
                print("[GENERATE] Cancelled by user")
            except Exception as e:
                error_msg = str(e)
                print(f"[GENERATE] Error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                state.is_generating = False

            _questions = raw_questions
            _error = error_msg
            _cancelled = cancelled

            def on_complete():
                timer.cancel()
                state.bus.emit(EVT_ACTION_BAR_CHANGED)
                if _cancelled:
                    ui.notify("Generation cancelled", type="warning")
                    return
                if _error:
                    ui.notify(f"Generation failed: {_error}", type="negative")
                    return

                unique_qs = []
                dupe_qs = []
                for q in _questions:
                    all_stems = [eq.stem for eq in state.generated_questions] + [uq.stem for uq in unique_qs]
                    if state.db.has_similar_stem(q.stem) or _stem_similar_to_any(q.stem, all_stems):
                        dupe_qs.append(q)
                    else:
                        unique_qs.append(q)

                for q in unique_qs:
                    state.generated_questions.append(q)

                state.bus.emit(EVT_QUESTIONS_CHANGED)

                if dupe_qs:
                    ui.notify(
                        f"{len(unique_qs)} unique, {len(dupe_qs)} duplicate(s) — regenerating duplicates...",
                        type="info",
                    )
                    _regenerate_duplicates(
                        state, refs, _callback_anchor, do_generate,
                        dupe_count=len(dupe_qs), attempt=1, max_attempts=3,
                    )
                else:
                    ui.notify(f"Generation complete — {len(unique_qs)} question(s)", type="positive")
                    if unique_qs and config.ollama_enabled and config.ollama_model:
                        auto_qa_batch(state, refs, _callback_anchor)

            with _callback_anchor:
                ui.timer(0, lambda: (on_complete(), False), once=True)

        thread = threading.Thread(target=run_and_finish, daemon=True)
        thread.start()
        state.bus.emit(EVT_ACTION_BAR_CHANGED)

    refs.on_generate = on_generate

    def on_generate_batch():
        """Trigger question generation for ALL slides with speaker notes."""
        if state.is_generating:
            return
        if not config.ollama_enabled:
            ui.notify("Ollama is disabled — enable it in AI & Docs", type="warning")
            return
        if not config.ollama_model:
            ui.notify("No Ollama model selected — check AI & Docs", type="warning")
            return

        f = state.selected_file
        if not f or not f.reader:
            ui.notify("No file loaded — add a PPTX first", type="warning")
            return

        cert_id = f.certification_id or state.active_cert_id
        if not cert_id:
            ui.notify("Select a certification first (sidebar)", type="warning")
            return

        batch_slides = []
        batch_image_paths = []
        for i in range(f.slide_count):
            sl = f.reader.get_slide(i)
            if sl and sl.speaker_notes and sl.speaker_notes.strip():
                batch_slides.append(sl)
                img = f.slide_images[i] if i < len(f.slide_images) else None
                batch_image_paths.append(str(img) if img and img.exists() else None)

        if not batch_slides:
            ui.notify("No slides with speaker notes found in this file", type="warning")
            return

        if refs.tabs and refs.generate_tab:
            refs.tabs.set_value(refs.generate_tab)

        state.is_generating = True
        state._cancel_generation = False
        state.progress_fraction = 0
        state._gen_start_time = time.time()

        difficulty = config.default_difficulty
        bloom = config.default_bloom_level
        file_topic = (f.topic if f else "") or ""
        include_scenario = getattr(state, '_gen_include_scenario', True)

        ui_specs = getattr(state, '_gen_question_specs', [{"keys": 1, "distractors": 3}])
        question_specs = _build_question_specs(ui_specs)
        num_per = len(question_specs)

        custom = ""
        if not include_scenario:
            custom = "Do NOT include a scenario. Leave the 'scenario' field as an empty string."
        if config.mermaid_enabled:
            custom += (
                "\n\nIn the 'explanation' field, when describing processes, workflows, or relationships, "
                "include a Mermaid diagram using a ```mermaid code fence. Use flowchart, sequence, "
                "state, or mindmap syntax as appropriate. Keep diagrams concise."
            )

        state.progress_message = f"Generating from {len(batch_slides)} slides — {num_per} question(s) per slide..."

        def do_generate_batch():
            def progress_cb(current, total, message):
                if state._cancel_generation:
                    raise InterruptedError("Generation cancelled by user")
                state.progress_fraction = current / total if total else 0
                state.progress_message = message

            return generate_questions_batch(
                slides=batch_slides,
                model=config.ollama_model,
                base_url=config.ollama_url,
                num_per_slide=num_per,
                difficulty=difficulty,
                bloom_level=bloom,
                certification_id=cert_id,
                source_file=f.path.name,
                system_prompt=config.system_prompt,
                progress_callback=progress_cb,
                topic=file_topic,
                custom_instructions=custom,
                slide_images=batch_image_paths,
                question_specs=question_specs,
            )

        with _callback_anchor:
            timer_batch = ui.timer(0.8, lambda: _poll_progress(state))

        def run_and_finish_batch():
            raw_questions = []
            error_msg = ""
            cancelled = False
            try:
                print(f"[GENERATE BATCH] Starting for {len(batch_slides)} slides...")
                raw_questions = do_generate_batch()
                print(f"[GENERATE BATCH] Got {len(raw_questions)} question(s) from AI")
            except InterruptedError:
                cancelled = True
                print("[GENERATE BATCH] Cancelled by user")
            except Exception as e:
                error_msg = str(e)
                print(f"[GENERATE BATCH] Error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                state.is_generating = False

            _questions = raw_questions
            _error = error_msg
            _cancelled = cancelled

            def on_complete_batch():
                timer_batch.cancel()
                state.bus.emit(EVT_ACTION_BAR_CHANGED)
                if _cancelled:
                    ui.notify("Batch generation cancelled", type="warning")
                    return
                if _error:
                    ui.notify(f"Batch generation failed: {_error}", type="negative")
                    return

                unique_qs = []
                dupe_count = 0
                for q in _questions:
                    all_stems = [eq.stem for eq in state.generated_questions] + [uq.stem for uq in unique_qs]
                    if state.db.has_similar_stem(q.stem) or _stem_similar_to_any(q.stem, all_stems):
                        dupe_count += 1
                    else:
                        unique_qs.append(q)

                for q in unique_qs:
                    state.generated_questions.append(q)

                state.bus.emit(EVT_QUESTIONS_CHANGED)

                msg = f"Batch complete — {len(unique_qs)} unique question(s) from {len(batch_slides)} slides"
                if dupe_count:
                    msg += f" ({dupe_count} duplicate(s) skipped)"
                ui.notify(msg, type="positive")

                if unique_qs and config.ollama_enabled and config.ollama_model:
                    auto_qa_batch(state, refs, _callback_anchor)

            with _callback_anchor:
                ui.timer(0, lambda: (on_complete_batch(), False), once=True)

        thread = threading.Thread(target=run_and_finish_batch, daemon=True)
        thread.start()
        state.bus.emit(EVT_ACTION_BAR_CHANGED)

    refs.on_generate_batch = on_generate_batch


# ── Private helpers ───────────────────────────────────────


def _build_question_specs(ui_specs):
    """Convert UI spec dicts to generation spec dicts."""
    question_specs = []
    for sp in ui_specs:
        nk = sp["keys"]
        nd = sp["distractors"]
        if nk > 1:
            question_specs.append({"type": "multi", "num_correct": nk, "num_choices": nk + nd})
        else:
            question_specs.append({"type": "single", "num_choices": 1 + nd})
    return question_specs


def _poll_progress(state):
    """Update elapsed time in progress message and refresh action bar."""
    if not state.is_generating:
        return
    elapsed = int(time.time() - state._gen_start_time)
    base_msg = state.progress_message
    if " (" in base_msg and "s)" in base_msg:
        base_msg = base_msg[:base_msg.rfind(" (")]
    state.progress_message = f"{base_msg} ({elapsed}s)"
    state.bus.emit(EVT_ACTION_BAR_CHANGED)


def _generate_from_docs(state, cert_id, cert, file_topic, num_per, difficulty, bloom,
                        custom, question_specs, progress_cb):
    """Generate questions from MCP documentation sources."""
    search_query = file_topic or cert.name
    selected_urls = state.active_mcp_servers
    if selected_urls:
        use_servers = [s for s in config.mcp_servers if s.get("url") in selected_urls]
    else:
        use_servers = config.mcp_servers

    all_search_results = []
    for srv in use_servers:
        url = srv.get("url", "")
        if not url:
            continue
        try:
            sr = mcp_client.search_documentation(search_query, url)
            srv_name = srv.get("name", url)
            for r in sr:
                r.title = f"{r.title} [{srv_name}]"
            all_search_results.extend(sr)
        except Exception:
            pass

    if not all_search_results:
        raise RuntimeError(f"No documentation found for '{search_query}'")

    parts_doc, total_chars = [], 0
    doc_links = []
    for r in all_search_results[:8]:
        snippet = r.content[:600] if len(r.content) > 600 else r.content
        entry = f"[{r.title}]({r.link})\n{snippet}"
        if total_chars + len(entry) > 6000:
            break
        parts_doc.append(entry)
        total_chars += len(entry)
        if r.link:
            doc_links.append(r.link)
    doc_content = "--- Relevant Documentation ---\n" + "\n\n".join(parts_doc) + "\n--- End Documentation ---"

    from ...core.pptx_reader import SlideInfo
    doc_slide = SlideInfo(
        index=0,
        title=search_query,
        body_text="",
        speaker_notes=doc_content,
    )
    results = generate_questions_batch(
        slides=[doc_slide],
        model=config.ollama_model,
        base_url=config.ollama_url,
        num_per_slide=num_per,
        difficulty=difficulty,
        bloom_level=bloom,
        certification_id=cert_id,
        source_file=f"docs:{search_query}",
        system_prompt=config.system_prompt,
        progress_callback=progress_cb,
        topic=file_topic,
        custom_instructions=custom,
        question_specs=question_specs,
    )
    unique_links = list(dict.fromkeys(doc_links))
    for q in results:
        q.source_type = "docs"
        q.source_slides = []
        q.key_source_slide = -1
        q.source_links = unique_links
    return results


def _generate_from_pcm(state, cert_id, cert, num_per, difficulty, bloom,
                       custom, question_specs, progress_cb):
    """Generate questions from a Pentaho Content Manager course's content.

    Reads the course's lab guides into per-section SlideInfo and generates
    num_per question(s) per section. Passing topic="" lets each question
    inherit its section title as the topic (→ the PCM `module` label).
    """
    from ...core.pcm_reader import load_pcm_course

    slug = cert.source_ref
    lab_slug = getattr(state, "pcm_lab_slug", "") or ""
    slides = load_pcm_course(config.pcm_courses_dir, slug, lab_slug)
    if not slides:
        scope = f"{slug}/{lab_slug}" if lab_slug else slug
        raise RuntimeError(
            f"No readable content for PCM course '{scope}' in {config.pcm_courses_dir}"
        )
    source_file = f"pcm:{slug}/{lab_slug}" if lab_slug else f"pcm:{slug}"
    results = generate_questions_batch(
        slides=slides,
        model=config.ollama_model,
        base_url=config.ollama_url,
        num_per_slide=num_per,
        difficulty=difficulty,
        bloom_level=bloom,
        certification_id=cert_id,
        source_file=source_file,
        system_prompt=config.system_prompt,
        progress_callback=progress_cb,
        topic="",  # per-section: question inherits slide.title as topic
        custom_instructions=custom,
        question_specs=question_specs,
    )
    for q in results:
        q.source_type = "pcm"
        q.source_links = []
    return results


def _regenerate_duplicates(state, refs, _callback_anchor, do_generate,
                           dupe_count, attempt, max_attempts):
    """Regenerate questions to replace duplicates, up to max_attempts."""
    if attempt > max_attempts or dupe_count <= 0:
        if dupe_count > 0:
            ui.notify(
                f"Could not replace {dupe_count} duplicate(s) after {max_attempts} attempts",
                type="warning",
            )
        if state.generated_questions and config.ollama_enabled and config.ollama_model:
            auto_qa_batch(state, refs, _callback_anchor)
        return

    state.progress_message = f"Regenerating {dupe_count} duplicate(s) (attempt {attempt}/{max_attempts})..."
    state.is_generating = True
    state.bus.emit(EVT_ACTION_BAR_CHANGED)

    def do_regen():
        try:
            return do_generate()
        except Exception as e:
            print(f"[REGEN] Error: {e}")
            return []
        finally:
            state.is_generating = False

    def on_regen_done(new_qs):
        state.bus.emit(EVT_ACTION_BAR_CHANGED)
        if not new_qs:
            ui.notify(f"Regeneration attempt {attempt} produced no questions", type="warning")
            _regenerate_duplicates(state, refs, _callback_anchor, do_generate,
                                  dupe_count, attempt + 1, max_attempts)
            return

        new_unique = []
        still_dupes = 0
        for q in new_qs:
            all_stems = [eq.stem for eq in state.generated_questions] + [uq.stem for uq in new_unique]
            if state.db.has_similar_stem(q.stem) or _stem_similar_to_any(q.stem, all_stems):
                still_dupes += 1
            else:
                new_unique.append(q)
                if len(new_unique) >= dupe_count:
                    break

        for q in new_unique:
            state.generated_questions.append(q)
        state.bus.emit(EVT_QUESTIONS_CHANGED)

        remaining = dupe_count - len(new_unique)
        if remaining > 0:
            ui.notify(
                f"Got {len(new_unique)} unique replacement(s), {remaining} still needed...",
                type="info",
            )
            _regenerate_duplicates(state, refs, _callback_anchor, do_generate,
                                  remaining, attempt + 1, max_attempts)
        else:
            ui.notify(
                f"All duplicates replaced — {len(state.generated_questions)} total question(s)",
                type="positive",
            )
            if config.ollama_enabled and config.ollama_model:
                auto_qa_batch(state, refs, _callback_anchor)

    def run_regen():
        result = do_regen()
        with _callback_anchor:
            ui.timer(0, lambda: (on_regen_done(result), False), once=True)

    threading.Thread(target=run_regen, daemon=True).start()
