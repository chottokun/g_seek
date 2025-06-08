# Streamlit Development and Debugging Tips

This document summarizes key learnings and tips derived from debugging complex issues within the Streamlit application, particularly concerning state management and interactions with background processes or external calls.

## Case Study: The "Disappearing UI" on Follow-up Questions

A critical bug was encountered where the Streamlit UI would turn white or "disappear" entirely when a user submitted a follow-up question. This happened without any Python exceptions being displayed in the Streamlit UI or logged in the standard server console, making it very difficult to diagnose.

### Problem Summary

- **Symptom**: UI freezes/disappears immediately after an action (button click) that calls a method on an object stored in `st.session_state`.
- **Specific Context**: The method in the session state object (`ResearchLoop.answer_follow_up`) internally made an LLM call (`llm_client.generate_text()`).
- **Key Finding**: The issue occurred precisely when the method (`answer_follow_up`) returned control to the `streamlit_app.py` script *after* the internal LLM call had been made.
    - If the method returned *before* making the LLM call (e.g., returning a hardcoded string immediately), `streamlit_app.py` handled it fine.
    - If `streamlit_app.py` called `llm_client.generate_text()` *directly*, it also handled it fine.
    - The problem was specific to the sequence: Streamlit UI -> Call method on session state object -> Method makes LLM call -> Method returns -> Streamlit UI crashes.

### Effective Diagnostic Steps Used

1.  **Global Exception Handler in UI Code**: Wrapping the problematic Streamlit widget's callback logic (e.g., the content of an `if st.button(...):`) in a broad `try...except Exception as e:` block that then prints the full traceback to the UI using `st.text(traceback.format_exc())`. This was crucial for eventually catching Python-level errors that Streamlit might otherwise obscure during a `rerun` or state update.
    ```python
    # In streamlit_app.py
    # import traceback
    # try:
    #   # ... button logic ...
    # except Exception as e:
    #   st.error(f"An error occurred: {e}")
    #   st.text(traceback.format_exc())
    ```

2.  **Granular `print()` Debugging**: Adding `print()` statements (flushing to the server console) at very fine-grained steps:
    *   Inside the Streamlit callback, before and after calling the problematic method.
    *   Inside the problematic method (`answer_follow_up`), before and after its own critical calls (like the LLM call).
    *   This helped pinpoint exactly which line was executed last before the failure.

3.  **Isolating Components ("Divide and Conquer")**:
    *   **Hardcoded Returns**: Modifying the problematic method to return simple, hardcoded strings *before* its complex internal operations (like an LLM call) to see if the basic call/return mechanism was stable.
    *   **Post-Operation Hardcoded Returns**: Modifying the problematic method to perform its internal operations (like the LLM call) but then discard the actual result and return a simple, hardcoded string. This helped determine if the issue was the *act* of the internal operation vs. the *content* of its result.
    *   **Direct Calls**: Moving the complex operation (the LLM call) directly into the `streamlit_app.py` script (bypassing the session state object's method) to see if the operation itself was stable in the Streamlit context. This was a key test that worked and pointed to the solution.

4.  **Checking Return Types and Content**: When a function returns to Streamlit, if the UI fails, check:
    *   The `type()` of the returned data.
    *   Attempt `str(returned_data)` in a `try-except` immediately upon return in `streamlit_app.py`.
    *   Log the length and a snippet of the returned string. Extremely long strings or strings with unusual/unsupported characters can sometimes cause issues with UI components or Streamlit's internal handling. (In our case, this turned out not to be the primary issue, as even a hardcoded string returned after an LLM call caused failure).

### Final Solution for the "Disappearing UI"

The solution was to move the problematic operation (the `llm_client.generate_text()` call for follow-up answers) out of the `ResearchLoop.answer_follow_up` method and directly into the `streamlit_app.py` button handler. The `ResearchLoop` object (still in session state) was then only used to fetch its `llm_client` attribute, and its `format_follow_up_prompt` method was called.

This suggests that complex operations (especially those involving I/O, C-extensions, or potentially altering the internal state of shared objects in complex ways) performed within methods of objects stored in `st.session_state` might sometimes lead to instability when those methods return control to the Streamlit script, especially if Streamlit's own state management or rerun mechanisms are sensitive to these changes. Calling such operations more directly from the main Streamlit script appeared more stable.

## General Streamlit Development Tips from this Experience

1.  **State Management is Key**: Understand how `st.session_state` works. Be mindful of how and when objects in session state are modified.
2.  **`st.rerun()` Behavior**: `st.rerun()` stops the current script execution and restarts it from the top. Ensure application state is consistent *before* calling `st.rerun()`. Conditional `st.rerun()` (e.g., only rerunning on success, not on error) can prevent error-rerun loops and keep error messages visible.
3.  **Robust Error Handling in UI Callbacks**: Always wrap event handler logic (like button clicks) in `try-except` blocks. Use `st.error()` and `st.text(traceback.format_exc())` to display errors clearly in the UI, as Streamlit can sometimes suppress or obscure tracebacks that occur within callbacks, especially if followed by a `rerun`.
4.  **Logging vs. `print()`**: While `print()` is useful for immediate console output during debugging, structured logging (`import logging; logger = logging.getLogger(__name__)`) is better for application-level diagnostics. However, ensure your logger is configured to output where you expect in the Streamlit environment. Sometimes, `print()` is more reliable for quick, raw output during deep bug hunts.
5.  **Isolate Complex Operations**: If a complex operation (especially involving external calls, C-bindings, or significant state changes to shared objects) within a callback seems to cause instability, try to:
    *   Simplify its return value.
    *   Move the call more directly into the main script body if it proves more stable there.
    *   Consider if the object whose method is being called needs to be re-fetched or re-instantiated from session state more carefully.

By being mindful of these points, development and debugging of Streamlit applications can be made more manageable.
