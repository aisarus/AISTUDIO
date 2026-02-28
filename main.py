"""
AI Scene Studio — FastAPI Backend
Gemini-powered layer compositor for mobile AI artists
"""
import re, json, base64
from io import BytesIO
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from PIL import Image
from google import genai
from google.genai import types

app = FastAPI(title="AI Scene Studio")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ─── Config ────────────────────────────────────────────────────────
IMAGE_MODELS = ["gemini-2.5-flash-image", "gemini-2.0-flash-exp"]
TEXT_MODELS  = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]
CFG_IMG = types.GenerateContentConfig(response_modalities=["Text", "Image"])
NO_CHANGE  = "Keep everything else in the image exactly unchanged — same composition, same subjects."
STYLE_GUARD = "No watermarks, no text overlays, no logos. High quality output."
CHESS_BG   = "Render on a transparent/checkerboard background (like Photoshop) — no solid color bg."

# ─── Image utils ───────────────────────────────────────────────────
def b64_to_bytes(b64: str) -> bytes:
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    return base64.b64decode(b64)

def bytes_to_b64(b: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(b).decode()

def to_png(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.convert("RGBA").save(buf, "PNG")
    return buf.getvalue()

def extract_img(resp, model: str) -> bytes:
    for c in getattr(resp, "candidates", []) or []:
        for p in getattr(getattr(c, "content", None), "parts", []) or []:
            d = getattr(getattr(p, "inline_data", None), "data", None)
            if isinstance(d, bytes):
                return to_png(Image.open(BytesIO(d)))
            if isinstance(d, str):
                return to_png(Image.open(BytesIO(base64.b64decode(d))))
    txt = (getattr(resp, "text", "") or "")[:300]
    raise Exception(f"No image in response from [{model}]. Got: {txt}")

def detect_models(client: genai.Client):
    try:
        names = {m.name.split("/")[-1] for m in client.models.list() if m.name}
        img = next((m for m in IMAGE_MODELS if m in names), IMAGE_MODELS[0])
        txt = next((m for m in TEXT_MODELS  if m in names), TEXT_MODELS[0])
        return img, txt
    except Exception:
        return IMAGE_MODELS[0], TEXT_MODELS[0]

# ─── Prompt builders ───────────────────────────────────────────────
def layer_prompt(kind: str, main: str, obj: str, bg: str, lt: str, mood: str) -> str:
    base = f"Scene: {main}\nMood: {mood or 'neutral'}\n"
    if kind == "object":
        return (f"{base}Generate ONLY the isolated main subject/object.\n"
                f"Object: {obj or 'infer from scene'}\n"
                f"Lighting: {lt or 'neutral studio'}\n"
                f"{CHESS_BG}\n{STYLE_GUARD}")
    if kind == "light":
        return (f"{base}Generate ONLY a lighting/glow/atmosphere effects layer.\n"
                f"Lighting: {lt or 'cinematic volumetric light, soft bloom'}\n"
                f"Minimal geometry — light effects only.\n{CHESS_BG}\n{STYLE_GUARD}")
    if kind == "background":
        return (f"{base}Generate ONLY the background environment. No main subject in it.\n"
                f"Background: {bg or 'infer fitting background from scene'}\n"
                f"Lighting: {lt or 'match the mood'}\n{STYLE_GUARD}")
    if kind == "combo":
        return (f"Render the full scene as one unified image:\n"
                f"Scene: {main}\nMain object: {obj or 'infer'}\n"
                f"Background: {bg or 'infer'}\nLighting: {lt or 'infer'}\nMood: {mood}\n{STYLE_GUARD}")
    return main  # custom

def decompose_sync(client: genai.Client, text_model: str, prompt: str) -> dict:
    resp = client.models.generate_content(
        model=text_model,
        contents=(
            "Decompose this scene prompt into JSON with keys: object, background, light, mood. "
            "Short concrete values. No markdown, no code fences.\n\nPROMPT: " + prompt
        ),
        config=types.GenerateContentConfig(temperature=0.2),
    )
    txt = re.sub(r"```[a-z]*", "", getattr(resp, "text", "") or "").replace("```", "").strip()
    try:
        j = json.loads(txt)
        return {k: str(j.get(k, "")) for k in ["object", "background", "light", "mood"]}
    except Exception:
        return {"object": "", "background": "", "light": "", "mood": ""}

# ─── Request models ────────────────────────────────────────────────
class ConnectReq(BaseModel):
    apiKey: str

class GenLayerReq(BaseModel):
    apiKey: str
    imageModel: str
    textModel: str
    layerType: str          # object | background | light | combo | custom
    mainPrompt: str = ""
    objectPrompt: str = ""
    backgroundPrompt: str = ""
    lightPrompt: str = ""
    moodPrompt: str = ""
    customPrompt: str = ""

class GenAllReq(BaseModel):
    apiKey: str
    imageModel: str
    textModel: str
    mainPrompt: str
    objectPrompt: str = ""
    backgroundPrompt: str = ""
    lightPrompt: str = ""
    moodPrompt: str = ""

class EditReq(BaseModel):
    apiKey: str
    imageModel: str
    image: str              # base64
    instruction: str

class MergeReq(BaseModel):
    apiKey: str
    imageModel: str
    fgImage: str            # foreground base64
    bgImage: str            # background base64
    fgName: str
    bgName: str
    hint: str = ""

class ImproveReq(BaseModel):
    apiKey: str
    textModel: str
    text: str
    target: str

class DecomposeReq(BaseModel):
    apiKey: str
    textModel: str
    mainPrompt: str

# ─── Routes ────────────────────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.post("/api/connect")
async def connect(req: ConnectReq):
    try:
        c = genai.Client(api_key=req.apiKey)
        im, tm = detect_models(c)
        # Sanity-test the key with a tiny text call
        c.models.generate_content(
            model=tm,
            contents="Reply with just the word OK.",
            config=types.GenerateContentConfig(max_output_tokens=5),
        )
        return {"imageModel": im, "textModel": tm}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/generate-layer")
async def gen_layer(req: GenLayerReq):
    try:
        c = genai.Client(api_key=req.apiKey)
        if req.layerType == "custom":
            prompt = req.customPrompt
        else:
            prompt = layer_prompt(
                req.layerType, req.mainPrompt, req.objectPrompt,
                req.backgroundPrompt, req.lightPrompt, req.moodPrompt
            )
        resp = c.models.generate_content(model=req.imageModel, contents=prompt, config=CFG_IMG)
        return {"image": bytes_to_b64(extract_img(resp, req.imageModel))}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/generate-all")
async def gen_all(req: GenAllReq):
    try:
        c = genai.Client(api_key=req.apiKey)
        # Auto-decompose if sub-prompts are empty
        if not req.objectPrompt and not req.backgroundPrompt:
            dec = decompose_sync(c, req.textModel, req.mainPrompt)
        else:
            dec = {
                "object":     req.objectPrompt,
                "background": req.backgroundPrompt,
                "light":      req.lightPrompt,
                "mood":       req.moodPrompt,
            }
        results = {}
        for kind in ["object", "background", "light", "combo"]:
            p = layer_prompt(kind, req.mainPrompt, dec["object"], dec["background"],
                             dec["light"], dec["mood"])
            resp = c.models.generate_content(model=req.imageModel, contents=p, config=CFG_IMG)
            results[kind] = bytes_to_b64(extract_img(resp, req.imageModel))
        return {"layers": results, "decomposed": dec}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/edit")
async def edit(req: EditReq):
    try:
        c = genai.Client(api_key=req.apiKey)
        resp = c.models.generate_content(
            model=req.imageModel,
            contents=[
                types.Part.from_bytes(data=b64_to_bytes(req.image), mime_type="image/png"),
                types.Part.from_text(text=req.instruction + "\n" + NO_CHANGE),
            ],
            config=CFG_IMG,
        )
        return {"image": bytes_to_b64(extract_img(resp, req.imageModel))}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/merge")
async def merge(req: MergeReq):
    try:
        c = genai.Client(api_key=req.apiKey)
        extra = f"\nExtra blending note: {req.hint}" if req.hint.strip() else ""
        instr = (
            f"Composite these two layers into one cohesive image:\n"
            f"  • Image 1 = FOREGROUND (top layer): {req.fgName}\n"
            f"  • Image 2 = BACKGROUND (bottom layer): {req.bgName}\n\n"
            f"Place foreground elements naturally in front of the background. "
            f"Match lighting, blend edges seamlessly. One unified final image. "
            f"No new objects added. No watermarks.{extra}"
        )
        resp = c.models.generate_content(
            model=req.imageModel,
            contents=[
                types.Part.from_bytes(data=b64_to_bytes(req.fgImage), mime_type="image/png"),
                types.Part.from_bytes(data=b64_to_bytes(req.bgImage), mime_type="image/png"),
                types.Part.from_text(text=instr),
            ],
            config=CFG_IMG,
        )
        return {"image": bytes_to_b64(extract_img(resp, req.imageModel))}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/improve")
async def improve(req: ImproveReq):
    try:
        c = genai.Client(api_key=req.apiKey)
        resp = c.models.generate_content(
            model=req.textModel,
            contents=(
                f"Improve this image editing/generation prompt for target '{req.target}'. "
                f"Keep the intent, make it more specific and visually descriptive. "
                f"Output ONLY the improved prompt text, nothing else.\n\nPROMPT: {req.text}"
            ),
            config=types.GenerateContentConfig(temperature=0.35),
        )
        return {"text": (getattr(resp, "text", "") or "").strip()}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/decompose")
async def decompose(req: DecomposeReq):
    try:
        c = genai.Client(api_key=req.apiKey)
        return decompose_sync(c, req.textModel, req.mainPrompt)
    except Exception as e:
        raise HTTPException(500, str(e))
