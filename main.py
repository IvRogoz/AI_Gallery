import os
import sys
import array
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

import dearpygui.dearpygui as dpg
from win32api import GetSystemMetrics

# Pillow optional
try:
    from PIL import Image

    PIL_OK = True
except Exception:
    PIL_OK = False

THUMB_SIZE = 192
THUMB_PADDING = 8
SIDEBAR_WIDTH = 320
SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp"}

state: Dict[str, object] = {
    "root_dir": str(Path.home()),
    "current_dir": str(Path.home()),
    "images_in_dir": [],
    "thumb_tex": {},
    "thumb_items": [],
    "grid_table": None,
    "grid_child": None,
    "texreg": "texreg",
    "frames": 0,
}


def is_image_file(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in SUPPORTED_EXT


def list_subdirs(p: Path) -> List[Path]:
    try:
        return sorted((x for x in p.iterdir() if x.is_dir()), key=lambda x: x.name.lower())
    except Exception:
        return []


def list_images(p: Path) -> List[str]:
    try:
        return [str(x) for x in sorted(p.iterdir(), key=lambda x: x.name.lower()) if is_image_file(x)]
    except Exception:
        return []


def pil_to_dpg(image: "Image.Image") -> Tuple[int, int, List[float]]:
    img = image.convert("RGBA")
    w, h = img.size
    data = [b / 255.0 for b in array.array("B", img.tobytes())]
    return w, h, data


def thumb_for(path: str):
    if not PIL_OK:
        return None
    tex = state["thumb_tex"].get(path)
    if tex:
        return tex
    try:
        from PIL import Image

        im = Image.open(path)
        im.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)
        w, h, data = pil_to_dpg(im)
        tex = dpg.add_static_texture(w, h, data, parent=state["texreg"])
        state["thumb_tex"][path] = tex
        return tex
    except Exception:
        return None


def available_grid_width() -> int:
    if not state["grid_child"]:
        return 800
    w = dpg.get_item_rect_size(state["grid_child"])[0]
    return w if w > 0 else 800


def compute_columns(avail_w: int) -> int:
    return max(1, avail_w // (THUMB_SIZE + THUMB_PADDING))


def open_system_viewer(image_path: str):
    if sys.platform.startswith("win"):
        os.startfile(image_path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", image_path])
    else:
        subprocess.Popen(["xdg-open", image_path])


def launch_viewer(image_path: str):
    try:
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--view", image_path], close_fds=True)
    except Exception:
        open_system_viewer(image_path)


def on_choose_root():
    dpg.configure_item("dir_dialog", show=True)


def on_dir_chosen(sender, app_data):
    sel = app_data.get("file_path_name")
    if sel and os.path.isdir(sel):
        set_root_directory(sel)


def on_open_in_explorer():
    p = state["current_dir"]
    if sys.platform.startswith("win"):
        os.startfile(p)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", p])
    else:
        subprocess.Popen(["xdg-open", p])


def on_folder_click(sender, app_data, user_data):
    load_directory_images(user_data)
    build_thumbnail_grid()


def on_thumb_double(sender, app_data, user_data):
    # launch separate process (another DPG instance) for full-size view
    launch_viewer(user_data)


def set_root_directory(path: str):
    state["root_dir"] = path
    load_directory_images(path)
    rebuild_sidebar_tree()
    build_thumbnail_grid()


def load_directory_images(path: str):
    state["current_dir"] = path
    state["images_in_dir"] = list_images(Path(path))
    dpg.set_value("path_label", path)


def rebuild_sidebar_tree():
    try:
        dpg.configure_item("sidebar_tree", label=Path(state["root_dir"]).name)
    except Exception:
        pass
    kids = dpg.get_item_children("sidebar_tree", 1) or []
    for ch in kids:
        dpg.delete_item(ch)
    root = Path(state["root_dir"])
    for sub in list_subdirs(root):
        nid = dpg.add_tree_node(label=sub.name, parent="sidebar_tree", default_open=False, leaf=False)
        dpg.add_button(label="Open folder", parent=nid, user_data=str(sub), callback=on_folder_click)


def clear_grid_items():
    for it in state["thumb_items"]:
        if dpg.does_item_exist(it):
            dpg.delete_item(it)
    state["thumb_items"].clear()
    if state["grid_table"] and dpg.does_item_exist(state["grid_table"]):
        dpg.delete_item(state["grid_table"])
        state["grid_table"] = None


def build_thumbnail_grid():
    clear_grid_items()
    cols = compute_columns(available_grid_width())
    with dpg.table(
        header_row=False,
        resizable=False,
        policy=dpg.mvTable_SizingFixedFit,
        borders_innerH=False,
        borders_innerV=False,
        borders_outerH=False,
        borders_outerV=False,
        row_background=False,
        parent=state["grid_child"],
    ) as table_id:
        state["grid_table"] = table_id
        for _ in range(cols):
            dpg.add_table_column(init_width_or_weight=float(THUMB_SIZE + THUMB_PADDING))
        imgs = state["images_in_dir"]
        if not imgs:
            with dpg.table_row(parent=table_id):
                with dpg.table_cell():
                    msg = "No images in this folder." if PIL_OK else "Pillow not installed. Thumbs disabled."
                    state["thumb_items"].append(dpg.add_text(msg))
        else:
            row = None
            for i, p in enumerate(imgs):
                if i % cols == 0:
                    row = dpg.add_table_row(parent=table_id)
                with dpg.table_cell(parent=row):
                    tex = thumb_for(p)
                    with dpg.group(horizontal=False) as g:
                        if tex:
                            btn = dpg.add_image_button(texture_tag=tex, width=THUMB_SIZE, height=THUMB_SIZE)
                        else:
                            btn = dpg.add_button(label="Open", width=THUMB_SIZE, height=THUMB_SIZE)
                        # per-item handler registry for double-click
                        ihr = dpg.add_item_handler_registry()
                        dpg.add_item_double_clicked_handler(parent=ihr, user_data=p, callback=on_thumb_double)
                        dpg.bind_item_handler_registry(btn, ihr)
                        state["thumb_items"].append(ihr)
                        dpg.add_text(os.path.basename(p))
                        state["thumb_items"].append(g)

def resize_callback(sender, app_data):
    try:
        width, height = int(app_data[0]), int(app_data[1])
    except Exception:
        return
    dpg.configure_item("main_window", width=width, height=height - 30)
    build_thumbnail_grid()

def build_ui():
    with dpg.texture_registry(show=False, tag=state["texreg"]):
        pass
    with dpg.window(label="Image Browser", tag="main_window", width=900, height=820, no_scrollbar=True):
        with dpg.group(horizontal=True):
            dpg.add_button(label="Choose Root…", callback=on_choose_root)
            dpg.add_button(label="Open in Explorer", callback=on_open_in_explorer)
            dpg.add_spacer(width=8)
            dpg.add_text("Path:")
            dpg.add_text(state["current_dir"], tag="path_label")
            dpg.add_spacer(width=16)
            dpg.add_text("Frames:", color=(200, 200, 200))
            dpg.add_text("0", tag="frame_label", color=(100, 255, 100))
        dpg.add_separator()
        with dpg.group(horizontal=True):
            with dpg.child_window(width=SIDEBAR_WIDTH, height=-1, border=True):
                dpg.add_text("Folders", bullet=True)
                with dpg.child_window(height=-1, border=False):
                    dpg.add_tree_node(label="Root", tag="sidebar_tree", default_open=True)
            with dpg.child_window(height=-1, border=True, tag="grid_child") as gc:
                state["grid_child"] = gc
                dpg.add_text("Loading…")
    with dpg.file_dialog(directory_selector=True, show=False, callback=on_dir_chosen, tag="dir_dialog", modal=True, width=700, height=400):
        dpg.add_file_extension("", color=(0, 0, 0, 255))
    set_root_directory(state["root_dir"])

def viewer_mode(image_path: str):
    # If Pillow missing, just open system viewer
    if not PIL_OK:
        open_system_viewer(image_path)
        return
    dpg.create_context()
    try:
        from PIL import Image

        im = Image.open(image_path)
        im.thumbnail((1600, 1000), Image.LANCZOS)
        w, h, data = pil_to_dpg(im)
        with dpg.texture_registry(show=False):
            tex = dpg.add_static_texture(w, h, data)
    except Exception:
        open_system_viewer(image_path)
        return
    title = os.path.basename(image_path)
    vw = min(w + 40, 1800)
    vh = min(h + 100, 1200)
    with dpg.window(label=title, tag="main_window", width=vw - 20, height=vh - 60, no_scrollbar=True):
        dpg.add_image(tex)
    dpg.create_viewport(title=f"Image Viewer — {title}", width=vw, height=vh, x_pos=100, y_pos=100, always_on_top=True)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    if hasattr(dpg, "set_primary_window"):
        dpg.set_primary_window("main_window", True)
    while dpg.is_dearpygui_running():
        dpg.render_dearpygui_frame()
    dpg.destroy_context()

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--view":
        viewer_mode(sys.argv[2])
        sys.exit(0)

    # Main app
    dpg.create_context()
    build_ui()

    screen_width = GetSystemMetrics(0)
    screen_height = GetSystemMetrics(1)
    vw = max(800, screen_width - 260)
    vh = max(600, screen_height - 30)

    dpg.create_viewport(title="Image Browser — frames: 0", width=vw, height=vh, x_pos=280, y_pos=0, always_on_top=True)

    dpg.set_viewport_resize_callback(resize_callback)
    dpg.setup_dearpygui()
    dpg.show_viewport()

    resize_callback(None, [vw, vh])

    # render loop
    last_w = 0
    last_title = 0
    while dpg.is_dearpygui_running():
        state["frames"] += 1
        dpg.set_value("frame_label", str(state["frames"]))
        if state["frames"] - last_title >= 10:
            dpg.set_viewport_title(f"Image Browser — frames: {state['frames']}")
            last_title = state["frames"]
        if state["grid_child"]:
            gw = dpg.get_item_rect_size(state["grid_child"])[0]
            if gw and gw != last_w:
                last_w = gw
                build_thumbnail_grid()
        dpg.render_dearpygui_frame()

    dpg.destroy_context()
