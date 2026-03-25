"""
src/seo_generator.py
─────────────────────
Generate YouTube Shorts SEO metadata using Claude (preferred) or GPT-4 (fallback).
Returns a structured dict with title, description, tags, hashtags, category_id, language.

Filename Hints System:
- Use #hashtags in filename: "video #Shorts #3DAnimation.mp4"
- Use @keywords: "video @medical @anatomy.mp4"
- Use | separators: "video | heart | beating.mp4"
- Use - keywords: "video-heart-beating-anatomy.mp4"
- Language hint: filename ending with _hi, _en, _hindi, _english
"""

import json
import logging
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = logging.getLogger(__name__)


def extract_filename_hints(file_name: str) -> dict:
    """
    Extract SEO hints from the filename.
    
    Supported formats:
    - #hashtags: "video #Shorts #3DAnimation.mp4" → ["Shorts", "3DAnimation"]
    - @keywords: "video @medical @anatomy.mp4" → ["medical", "anatomy"]
    - | separator: "video | heart | beating.mp4" → ["heart", "beating"]
    - - separator: "video-heart-beating.mp4" → ["heart", "beating"]
    - _hi/_en suffix: "video_hi.mp4" → language="hi"
    """
    hints = {
        "keywords": [],
        "hashtags": [],
        "language": None,
    }
    
    name_without_ext = os.path.splitext(file_name)[0]
    
    # Extract #hashtags
    hash_tags = re.findall(r'#(\w+)', name_without_ext)
    hints["hashtags"].extend(hash_tags)
    
    # Extract @keywords
    at_keywords = re.findall(r'@(\w+)', name_without_ext)
    hints["keywords"].extend(at_keywords)
    
    # Extract | separated words
    if '|' in name_without_ext:
        pipe_words = [w.strip() for w in name_without_ext.split('|') if w.strip()]
        for word in pipe_words:
            word_clean = re.sub(r'^[#@]', '', word).strip()
            if word_clean and word_clean.lower() not in ['shorts', 'youtubeshorts']:
                hints["keywords"].append(word_clean)
    
    # Extract - separated words (last resort, lower priority)
    dash_parts = name_without_ext.split('-')
    if len(dash_parts) > 1:
        for part in dash_parts:
            part_clean = part.strip()
            if (part_clean and 
                part_clean.lower() not in ['shorts', 'youtubeshorts', 'ytshorts'] and
                part_clean not in hints["keywords"] and
                part_clean not in hints["hashtags"]):
                # Only add if looks like a word (alphanumeric)
                if re.match(r'^[a-zA-Z0-9]+$', part_clean):
                    hints["keywords"].append(part_clean.lower())
    
    # Detect language from suffix
    name_lower = name_without_ext.lower()
    if name_lower.endswith('_hi') or name_lower.endswith('_hindi'):
        hints["language"] = "hi"
    elif name_lower.endswith('_en') or name_lower.endswith('_english'):
        hints["language"] = "en"
    
    # Remove duplicates
    hints["keywords"] = list(dict.fromkeys(hints["keywords"]))
    hints["hashtags"] = list(dict.fromkeys(hints["hashtags"]))
    
    logger.debug("Extracted filename hints: %s", hints)
    return hints

# Default fallback metadata used if AI call fails twice
FALLBACK_METADATA = {
    "title": "What Happens Inside Your Body 🔬",
    "description": (
        "Watch this incredible 3D breakdown of how your body works!\n"
        "Learn amazing facts about human anatomy in this detailed simulation.\n"
        "Subscribe to The 3D Breakdown for more!\n"
        "#Shorts #3DBreakdown #Anatomy #Science #Education"
    ),
    "tags": [
        "The 3D Breakdown",
        "3D animation",
        "3D simulation",
        "anatomy animation",
        "x-ray view",
        "educational shorts",
        "how it works",
        "Zack D Films style",
        "science explained",
        "CGI animation",
        "human anatomy",
        "body facts",
        "medical animation",
        "educational video",
        "science facts",
    ],
    "hashtags": ["#Shorts", "#3DBreakdown", "#Anatomy", "#Science", "#Education"],
    "category_id": "22",
    "default_language": "en",
}

SEO_SYSTEM_PROMPT = """You are a YouTube SEO expert for a 3D animation educational Shorts channel called "The 3D Breakdown". The channel explains science, anatomy, survival, history, and bizarre real-world events using 3D CGI animation, X-Ray views, and medical simulations. Style is similar to Zack D. Films.

Generate metadata in EXACTLY this JSON format:

{
  "title": "Curiosity hook title under 60 characters with 1 emoji at end",
  "description": "Line 1: Curiosity hook\\nLine 2: What viewer will learn\\nLine 3: Subscribe CTA\\nLine 4: 3-5 hashtags",
  "tags": ["specific_tag1", "specific_tag2", "broad_tag1", "broad_tag2", "channel_tag1"],
  "hashtags": ["#Shorts", "#3DBreakdown", "#TopicTag1", "#TopicTag2"],
  "category_id": "22",
  "default_language": "en"
}

STRICT RULES:

TITLE (50-60 chars max):
- Create curiosity - make viewer NEED to watch
- Add 1 relevant emoji at the END
- NO keyword stuffing
- Example: "What Really Happens When You Hold Your Breath 😮"

DESCRIPTION (under 150 words):
- Line 1: Curiosity hook related to topic
- Line 2: What viewer will learn from this video
- Line 3: CTA → "Subscribe to The 3D Breakdown for more!"
- Line 4: 3-5 hashtags → ALWAYS: #Shorts #3DBreakdown, then 2-3 topic-specific

TAGS (30-35 tags total):
- First: Specific topic tags (e.g., 'how ladybugs fold wings', 'transparent shell experiment')
- Then: Broad category tags (e.g., '3D animation', 'educational shorts', 'science explained')
- ALWAYS include: 'The 3D Breakdown', '3D animation', '3D simulation', 'anatomy animation', 'x-ray view', 'educational shorts', 'how it works', 'Zack D Films style', 'science explained', 'CGI animation'

CHANNEL IDENTITY:
- Channel name: "The 3D Breakdown"
- Style: Zack D. Films, 3D CGI animation, X-Ray views, medical simulations
- Topics: science, anatomy, survival, history, bizarre real-world events

IMPORTANT:
- Use the filename hints (keywords/hashtags) provided to prioritize topic-specific tags
- Output ONLY valid JSON, no markdown, no code fences, no extra text
- Language: English (or Hindi if language hint is '_hi')"""


def _generate_with_anthropic(file_name: str, hints: dict) -> dict:
    """Call Claude API to generate SEO metadata."""
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    
    hints_text = ""
    if hints["keywords"]:
        hints_text += f"Keywords from filename: {', '.join(hints['keywords'])}\n"
    if hints["hashtags"]:
        hints_text += f"Hashtags from filename: {', '.join(['#' + h for h in hints['hashtags']])}\n"
    if hints["language"]:
        hints_text += f"Language hint: {'Hindi' if hints['language'] == 'hi' else 'English'}\n"
    
    user_message = (
        f"Video filename: {file_name}\n\n"
        f"{hints_text}"
        "Generate complete YouTube Shorts SEO metadata for this video. "
        "Prioritize the keywords and hashtags extracted from the filename. "
        "If language hint is given, use that language for title/description."
    )

    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        system=SEO_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    raw = message.content[0].text.strip()
    logger.debug("Claude raw response: %s", raw)
    return json.loads(raw)


def _generate_with_openai(file_name: str, hints: dict) -> dict:
    """Call OpenAI GPT-4 to generate SEO metadata."""
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    hints_text = ""
    if hints["keywords"]:
        hints_text += f"Keywords from filename: {', '.join(hints['keywords'])}\n"
    if hints["hashtags"]:
        hints_text += f"Hashtags from filename: {', '.join(['#' + h for h in hints['hashtags']])}\n"
    if hints["language"]:
        hints_text += f"Language hint: {'Hindi' if hints['language'] == 'hi' else 'English'}\n"
    
    user_message = (
        f"Video filename: {file_name}\n\n"
        f"{hints_text}"
        "Generate complete YouTube Shorts SEO metadata for this video. "
        "Prioritize the keywords and hashtags extracted from the filename. "
        "If language hint is given, use that language for title/description."
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SEO_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        max_tokens=1024,
        temperature=0.7,
    )
    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        raise ValueError("OpenAI returned empty content")
    logger.debug("OpenAI raw response: %s", raw)
    return json.loads(raw)


CHANNEL_REQUIRED_TAGS = [
    "The 3D Breakdown",
    "3D animation",
    "3D simulation",
    "anatomy animation",
    "x-ray view",
    "educational shorts",
    "how it works",
    "Zack D Films style",
    "science explained",
    "CGI animation",
]


def _validate_metadata(metadata: dict, hints: dict | None = None) -> dict:
    """Validate and sanitize AI-generated metadata per The 3D Breakdown format."""
    
    # 1. TITLE: Ensure under 60 chars, has emoji at end
    raw_title = metadata.get("title") or FALLBACK_METADATA["title"]
    title = str(raw_title).strip()[:60]
    
    # Check for emoji at end, add if missing
    title_ends_emoji = any(ord(c) > 127 for c in title[-2:]) if len(title) >= 2 else False
    if not title_ends_emoji and len(title) > 0:
        title = title.strip() + " 🔬"
    title = title[:60]  # Re-trim after adding emoji
    
    # 2. DESCRIPTION: Ensure proper format
    raw_desc = metadata.get("description") or FALLBACK_METADATA["description"]
    description = str(raw_desc).strip()
    
    # Ensure proper line breaks format
    if "\\n" in description:
        description = description.replace("\\n", "\n")
    
    # Ensure hashtags at end
    if "#Shorts" not in description and "#shorts" not in description.lower():
        description = description.rstrip() + "\n\n#Shorts #3DBreakdown"
    elif "#3DBreakdown" not in description and "#3dbreakdown" not in description.lower():
        description = description.rstrip() + " #3DBreakdown"
    
    description = description[:5000]
    
    # 3. TAGS: Ensure 30-35 tags with channel tags
    raw_tags = metadata.get("tags")
    tags: list[str] = []
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    elif isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if t]
    else:
        tags = list(FALLBACK_METADATA["tags"])
    
    # Add filename hint keywords as tags if not present
    if hints and hints.get("keywords"):
        for kw in hints["keywords"]:
            kw_lower = kw.lower()
            if not any(kw_lower in t.lower() for t in tags):
                tags.insert(0, kw)
    
    # Ensure channel required tags are present
    for req_tag in CHANNEL_REQUIRED_TAGS:
        if req_tag not in tags:
            tags.append(req_tag)
    
    # Clean and prune tags for YouTube API requirements
    # - Each tag must be under 25 characters
    # - Only alphanumeric and spaces allowed
    # - No leading/trailing spaces, no special characters
    # - Total must be under 500 characters
    final_tags: list[str] = []
    current_length = 0
    for t in tags:
        # Clean tag: remove special chars, keep only alphanumeric and spaces
        t_clean = re.sub(r'[^a-zA-Z0-9 ]', '', str(t)).strip()
        # Limit to 24 chars max
        t_clean = t_clean[:24]
        # Skip if too short
        if not t_clean or len(t_clean) < 2:
            continue
        # Skip if already added
        if t_clean.lower() in [existing.lower() for existing in final_tags]:
            continue
        if current_length + len(t_clean) + 1 <= 500:
            final_tags.append(t_clean)
            current_length += len(t_clean) + 1
        else:
            break
    
    # 4. HASHTAGS: Ensure #Shorts #3DBreakdown are present
    raw_h = metadata.get("hashtags")
    hashtags: list[str] = []
    if isinstance(raw_h, str):
        hashtags = [h.strip() for h in raw_h.split() if h.strip()]
    elif isinstance(raw_h, list):
        hashtags = [str(h).strip() for h in raw_h if h]
    else:
        hashtags = list(FALLBACK_METADATA["hashtags"])
    
    # Add filename hint hashtags
    if hints and hints.get("hashtags"):
        for h in hints["hashtags"]:
            h_tag = f"#{h}"
            if h_tag not in hashtags:
                hashtags.insert(0, h_tag)
    
    # Ensure #Shorts and #3DBreakdown
    h_lower = [h.lower() for h in hashtags]
    if "#shorts" not in h_lower:
        hashtags.insert(0, "#Shorts")
    if "#3dbreakdown" not in h_lower:
        hashtags.insert(1, "#3DBreakdown")
    
    # Keep max 5 hashtags
    hashtags = hashtags[:5]

    return {
        "title": title,
        "description": description,
        "tags": final_tags,
        "hashtags": hashtags,
        "category_id": str(metadata.get("category_id", "22")),
        "default_language": str(metadata.get("default_language", "en")),
    }


def _generate_with_nvidia(file_name: str, hints: dict) -> dict:
    """Call NVIDIA API to generate SEO metadata using Nemotron."""
    from openai import OpenAI

    client = OpenAI(
        base_url=settings.NVIDIA_BASE_URL,
        api_key=settings.NVIDIA_API_KEY
    )
    
    hints_text = ""
    if hints["keywords"]:
        hints_text += f"Keywords from filename: {', '.join(hints['keywords'])}\n"
    if hints["hashtags"]:
        hints_text += f"Hashtags from filename: {', '.join(['#' + h for h in hints['hashtags']])}\n"
    if hints["language"]:
        hints_text += f"Language hint: {'Hindi' if hints['language'] == 'hi' else 'English'}\n"
    
    user_message = (
        f"Video filename: {file_name}\n\n"
        f"{hints_text}"
        "Generate complete YouTube Shorts SEO metadata for this video. "
        "Prioritize the keywords and hashtags extracted from the filename. "
        "If language hint is given, use that language for title/description. "
        "Return ONLY valid JSON, no markdown, no code blocks."
    )

    response = client.chat.completions.create(
        model=settings.NVIDIA_MODEL,
        messages=[
            {"role": "system", "content": SEO_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        max_tokens=1024,
        temperature=0.7,
        top_p=0.95,
        extra_body={
            "chat_template_kwargs": {"enable_thinking": False},
        }
    )
    
    # Get the raw content
    message = response.choices[0].message
    raw = message.content or ""
    
    # If content is empty, convert to string
    if not raw.strip():
        raw = str(message)
    
    raw = raw.strip()
    logger.debug("NVIDIA raw response: %s", raw[:500])
    
    if not raw:
        raise ValueError("NVIDIA returned empty content")
    
    # Extract JSON from response
    # First, try direct JSON parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    
    # Try to find JSON in the text
    import re
    # Look for JSON object pattern - find first { and last }
    start = raw.find('{')
    end = raw.rfind('}') + 1
    if start != -1 and end > start:
        try:
            extracted = raw[start:end]
            result = json.loads(extracted)
            if isinstance(result, dict) and 'title' in result:
                return result
        except json.JSONDecodeError:
            pass
    
    raise ValueError(f"Could not parse JSON from NVIDIA response: {raw[:200]}")


def generate_seo_metadata(file_name: str) -> dict:
    """
    Generate YouTube Shorts SEO metadata for the given video filename.

    Tries the configured AI provider first, retries once on failure,
    then falls back to default metadata.
    
    Uses filename hints system to improve SEO relevance:
    - #hashtags in filename → AI uses these
    - @keywords in filename → AI prioritizes these
    - | or - separators → AI extracts keywords
    - _hi/_en suffix → language hint
    """
    provider = settings.AI_PROVIDER
    logger.info("Generating SEO metadata using '%s' for: %s", provider, file_name)
    
    # Extract hints from filename
    hints = extract_filename_hints(file_name)
    if hints["keywords"] or hints["hashtags"]:
        logger.info("Filename hints detected: keywords=%s, hashtags=%s, language=%s",
                    hints["keywords"], hints["hashtags"], hints["language"])

    for attempt in range(1, 3):  # Try twice
        try:
            if provider == "nvidia":
                raw = _generate_with_nvidia(file_name, hints)
            elif provider == "anthropic":
                raw = _generate_with_anthropic(file_name, hints)
            else:
                raw = _generate_with_openai(file_name, hints)

            metadata = _validate_metadata(raw, hints)
            
            # Apply language hint if AI didn't set it
            if hints.get("language") and not metadata.get("default_language"):
                metadata["default_language"] = hints["language"]

            logger.info(
                "SEO metadata generated (attempt %d): title='%s', tags=%d",
                attempt, metadata["title"], len(metadata["tags"])
            )
            return metadata

        except json.JSONDecodeError as exc:
            logger.warning("Attempt %d: AI returned invalid JSON — %s", attempt, exc)
            if attempt == 1:
                time.sleep(2)
        except Exception as exc:
            logger.warning("Attempt %d: AI call failed — %s", attempt, exc)
            if attempt == 1:
                time.sleep(5)

    logger.warning("Both AI attempts failed. Using fallback metadata.")
    return FALLBACK_METADATA.copy()
