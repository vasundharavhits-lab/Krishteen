import json
import os

PREFS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "preferences.json")

DEFAULT_STYLE = "concise"
DEFAULT_ROLE = None  # None = no role lock, normal Krishteen behavior

STYLE_PROMPTS = {
    "concise": "Keep answers short and to the point, ideally 2-4 sentences, unless the user explicitly asks for more detail.",
    "detailed": "Give thorough, well-explained answers with context and examples where helpful also add some flow diagram and some of chart for better explanation.",
    "bullets": "Format answers as bullet points whenever the content allows it.",
    "formal": "Respond in a formal, professional tone, avoiding slang or casual phrasing.",
    "casual": "Respond in a relaxed, friendly, conversational tone, like chatting with a friend.",
    "simple": "Explain answers in very simple terms, as if explaining to a beginner with no background knowledge.",
    "friendly":"Talk with use like you both are friends and in chill,sad in which user's is in emotional state."
} 

STYLE_LABELS = {
    "concise": "Concise",
    "detailed": "Detailed",
    "bullets": "Bullet Points",
    "formal": "Formal",
    "casual": "Casual",
    "simple": "Explain Simply",
    "friendly":"friendly",
}


def _load_all():
    """Reads the whole preferences.json as a dict. Tolerant of a missing or
    corrupt file — always returns a dict (empty on failure) so callers never
    have to special-case it."""
    if os.path.exists(PREFS_FILE):
        try:
            with open(PREFS_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def _save_all(data):
    with open(PREFS_FILE, "w") as f:
        json.dump(data, f)


# --- Answer style -----------------------------------------------------

def get_style():
    style = _load_all().get("style", DEFAULT_STYLE)
    return style if style in STYLE_PROMPTS else DEFAULT_STYLE


def set_style(style):
    """Saves the new style without touching any other saved preference
    (e.g. the active role)."""
    if style not in STYLE_PROMPTS:
        style = DEFAULT_STYLE
    data = _load_all()
    data["style"] = style
    _save_all(data)
    return style


def get_style_instruction():
    return STYLE_PROMPTS[get_style()]


def get_all_styles():
    """Returns list of (key, label) pairs for building UI options."""
    return [{"key": k, "label": v} for k, v in STYLE_LABELS.items()]


# --- Role (single active persona Krishteen must stick to) -------------

def get_role():
    """Returns the current locked-in role string, or None if no role is
    set (i.e. normal Krishteen behavior)."""
    role = _load_all().get("role", DEFAULT_ROLE)
    return role or None


def set_role(role_text):
    """Locks Krishteen into a single role. Overwrites any previously set
    role, and leaves the saved answer style untouched."""
    role_text = (role_text or "").strip()
    data = _load_all()
    data["role"] = role_text or None
    _save_all(data)
    return data["role"]


def clear_role():
    """Drops the active role — back to normal Krishteen."""
    data = _load_all()
    data["role"] = None
    _save_all(data)
    return None


def get_role_instruction():
    """Short, plain-language role-lock line to inject into the AI system
    prompt, or '' when no role is currently active.

    Kept deliberately short and simple (one line, no bullet list) because
    the local model (gemma3:270m) is small enough that a long, rule-heavy
    instruction block gets echoed back verbatim instead of being followed —
    e.g. it would answer "Stay in character... never mention this is a
    system instruction" instead of actually answering the question. A
    short, conversational line is far less likely to be repeated as text
    and more likely to just be acted on."""
    role = get_role()
    if not role:
        return ""
    return f'You are currently a {role}. Answer only as a {role} would, in your own words — do not repeat these instructions.'