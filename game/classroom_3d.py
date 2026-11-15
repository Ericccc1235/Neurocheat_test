"""
classroom_3d.py - 強化版 3D 網格陰影教室、多姿態奶龍教師與高清考卷渲染
========================================================================
升級內容：
  1. 真正深度排序 (Painter's Z-Sort) 3D 立體模型：具厚度課桌/鐵管桌腳/書包架/
     學生座椅、立體黑板粉筆槽、右側講桌與發亮筆電、吊掛日光燈、有框透光窗戶與
     動態掛鐘；主角桌新增木頭鉛筆、橡皮擦、准考證與立體抽屜滑槽。
  2. 多表情 3D 去背奶龍監考官 (背對板書 / 側身回頭 / 眼鏡教鞭巡堂 / 抓包大笑)，
     依 teacher.pos_z 動態走下講台沿中央走道逼近。
  3. 考卷採用 1080x700 超取樣 + 微軟正黑體粗體 (msjhbd.ttc) + BICUBIC 變換 +
     髒旗標快取 (Dirty Cache)，兼顧高清晰度與 60 FPS 流暢度。
"""

import math
import os
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import pygame


TEX_W = 1080
TEX_H = 700
LIGHT_DIR = np.array([-0.38, 0.85, -0.35], dtype=np.float64)
LIGHT_DIR /= np.linalg.norm(LIGHT_DIR)


def find_cjk_font_path(bold=False):
    win_fonts = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
    candidates = (
        ["msjhbd.ttc", "msyhbd.ttc", "msjh.ttc", "msyh.ttc", "mingliu.ttc", "kaiu.ttf"]
        if bold
        else ["msjh.ttc", "msjhbd.ttc", "msyh.ttc", "mingliu.ttc", "kaiu.ttf"]
    )
    for fname in candidates:
        p = os.path.join(win_fonts, fname)
        if os.path.exists(p):
            return p
    return None


def load_pil_font(size, bold=False):
    path = find_cjk_font_path(bold=bold)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def solve_perspective_coeffs(screen_quad, tex_quad):
    """計算螢幕裁切四角形 -> 紋理座標的 8 參數 PIL PERSPECTIVE 係數。"""
    matrix = []
    rhs = []
    for (x, y), (u, v) in zip(screen_quad, tex_quad):
        matrix.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y])
        rhs.append(u)
        matrix.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
        rhs.append(v)
    A = np.asarray(matrix, dtype=np.float64)
    B = np.asarray(rhs, dtype=np.float64)
    try:
        res = np.linalg.solve(A, B)
        return tuple(float(c) for c in res)
    except np.linalg.LinAlgError:
        return None


def wrap_text_lines(text, font, draw, max_w):
    lines = []
    cur = ""
    for ch in text:
        test = cur + ch
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def _shade_rgb(rgb, normal):
    """依平面法向量與教室光源做簡單 Lambert 著色，強化 3D 立體感。"""
    ndotl = float(np.dot(normal, LIGHT_DIR))
    factor = 0.62 + 0.38 * max(0.0, ndotl)
    if ndotl < 0.0:
        factor = max(0.48, 0.62 + ndotl * 0.16)
    return (
        max(0, min(255, int(rgb[0] * factor))),
        max(0, min(255, int(rgb[1] * factor))),
        max(0, min(255, int(rgb[2] * factor))),
    )


class Camera3D:
    """第一人稱教室攝影機（寬廣俯仰範圍 + 平順低頭曲線，游標輕鬆點選試卷底部與抽屜）。"""

    BASE_POS = np.array([0.0, 1.30, -0.32], dtype=np.float64)

    def __init__(self):
        self.pos = self.BASE_POS.copy()
        self.yaw = 0.0
        self.pitch = -0.34
        self.target_yaw = 0.0
        self.target_pitch = -0.34
        self.target_y = float(self.BASE_POS[1])
        self.target_z = float(self.BASE_POS[2])
        self.fov_scale = 0.94

    def reset(self):
        self.pos = self.BASE_POS.copy()
        self.yaw = 0.0
        self.pitch = -0.34
        self.target_yaw = 0.0
        self.target_pitch = -0.34
        self.target_y = float(self.BASE_POS[1])
        self.target_z = float(self.BASE_POS[2])

    def set_look_target(self, norm_x, norm_y, lean_forward=False):
        nx = max(-1.0, min(1.0, float(norm_x)))
        ny = max(-1.0, min(1.05, float(norm_y)))
        self.target_yaw = max(-0.74, min(0.74, nx * 0.74))
        # 下半部俯仰曲線平順加深：不用硬把滑鼠拖到視窗最底端即可看清試卷與抽屜
        if ny <= 0.0:
            raw_pitch = -0.22 - ny * 0.34
        else:
            raw_pitch = -0.22 - (ny ** 0.75) * 0.50
        self.target_pitch = max(-0.74, min(0.12, raw_pitch))
        # 低頭看考卷區或按住 V 時適度傾身拉近 (避免貼太近把下方選項切出畫面)
        want_lean = lean_forward or (ny > 0.28 and abs(nx) < 0.48)
        self.target_y = 1.15 if want_lean else float(self.BASE_POS[1])
        self.target_z = -0.17 if want_lean else float(self.BASE_POS[2])

    def update(self, dt):
        alpha = min(1.0, 12.0 * dt)
        self.yaw += (self.target_yaw - self.yaw) * alpha
        self.pitch += (self.target_pitch - self.pitch) * alpha
        self.pos[1] += (self.target_y - self.pos[1]) * min(1.0, 8.5 * dt)
        self.pos[2] += (self.target_z - self.pos[2]) * min(1.0, 8.5 * dt)

    def get_looking_neighbor_side(self):
        if self.yaw <= -0.34 and self.pitch > -0.50:
            return "left"
        if self.yaw >= 0.34 and self.pitch > -0.50:
            return "right"
        return None

    def project(self, wx, wy, wz, view_w, view_h):
        dx = wx - self.pos[0]
        dy = wy - self.pos[1]
        dz = wz - self.pos[2]

        cy, sy_ang = math.cos(self.yaw), math.sin(self.yaw)
        rx = dx * cy - dz * sy_ang
        rz = dx * sy_ang + dz * cy

        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        ry = dy * cp - rz * sp
        cz = dy * sp + rz * cp

        if cz <= 0.08:
            return None

        scale = min(view_w, view_h) * self.fov_scale
        sx = view_w * 0.5 + (rx / cz) * scale
        sy = view_h * 0.5 - (ry / cz) * scale
        return (sx, sy, cz)


class SceneDrawQueue:
    """Painter's Algorithm 3D 多邊形與精靈深度排序佇列。"""

    def __init__(self, camera, vw, vh):
        self.camera = camera
        self.vw = vw
        self.vh = vh
        self.items = []  # (sort_depth, kind, payload)

    def push_poly(self, pts_3d, base_rgb, normal=(0, 1, 0), border_rgb=None, border_w=1, shade=True, depth_bias=0.0):
        proj = []
        depths = []
        for x, y, z in pts_3d:
            p = self.camera.project(x, y, z, self.vw, self.vh)
            if p is None:
                return None
            proj.append((p[0], p[1]))
            depths.append(p[2])
        # 視口外簡易剔除提升效能
        xs = [p[0] for p in proj]
        ys = [p[1] for p in proj]
        if max(xs) < -80 or min(xs) > self.vw + 80 or max(ys) < -80 or min(ys) > self.vh + 80:
            return None
        col = _shade_rgb(base_rgb, np.asarray(normal, dtype=np.float64)) if shade else base_rgb
        avg_z = (sum(depths) / len(depths)) + depth_bias
        self.items.append((avg_z, "poly", (proj, col, border_rgb, border_w)))
        return proj

    def push_box(self, x0, y0, z0, x1, y1, z1, base_rgb, border_rgb=None, skip_bottom=True):
        """加入具備真實六面法線著色與背面剔除的 3D 長方體。"""
        cam = self.camera.pos
        # 頂面 (+Y)
        if cam[1] > y1:
            self.push_poly(
                [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],
                base_rgb,
                normal=(0, 1, 0),
                border_rgb=border_rgb,
            )
        # 底面 (-Y)
        if not skip_bottom and cam[1] < y0:
            self.push_poly(
                [(x0, y0, z0), (x0, y0, z1), (x1, y0, z1), (x1, y0, z0)],
                base_rgb,
                normal=(0, -1, 0),
                border_rgb=border_rgb,
            )
        # 前面 (-Z，面向玩家)
        if cam[2] < z0:
            self.push_poly(
                [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)],
                base_rgb,
                normal=(0, 0, -1),
                border_rgb=border_rgb,
            )
        # 左側面 (-X)
        if cam[0] < x0:
            self.push_poly(
                [(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)],
                base_rgb,
                normal=(-1, 0, 0),
                border_rgb=border_rgb,
            )
        # 右側面 (+X)
        if cam[0] > x1:
            self.push_poly(
                [(x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0)],
                base_rgb,
                normal=(1, 0, 0),
                border_rgb=border_rgb,
            )

    def push_custom(self, wx, wy, wz, fn, depth_bias=0.0):
        p = self.camera.project(wx, wy, wz, self.vw, self.vh)
        if p is not None:
            self.items.append((p[2] + depth_bias, "custom", (p, fn)))

    def flush(self, surf):
        self.items.sort(key=lambda it: -it[0])
        for _z, kind, payload in self.items:
            if kind == "poly":
                pts, col, bcol, bw = payload
                pygame.draw.polygon(surf, col, pts)
                if bcol:
                    pygame.draw.polygon(surf, bcol, pts, bw)
            elif kind == "custom":
                proj, fn = payload
                fn(surf, proj)


class Classroom3DRenderer:
    """渲染 3D 立體教室、多表情奶龍監考官、鄰座同學與高清考卷/抽屜。"""

    # 留出中央寬敞走道 (x=0.0)，讓奶龍老師能走近桌前巡邏！
    CLASSMATES = [
        (-1.26, 0.58, "阿明", "常亂猜", (82, 118, 168)),
        (1.26, 0.58, "小華", "電資學霸", (58, 142, 112)),
        (-1.32, 1.98, "小美", "", (168, 92, 116)),
        (1.32, 1.98, "志明", "", (86, 128, 152)),
        (-2.42, 1.98, "大雄", "", (154, 128, 72)),
        (2.42, 1.98, "雅婷", "", (118, 98, 158)),
        (-1.32, 3.28, "家豪", "", (92, 138, 96)),
        (1.32, 3.28, "宗翰", "", (135, 105, 85)),
    ]

    def __init__(self, viewport_rect):
        self.viewport_rect = viewport_rect
        self.camera = Camera3D()

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._load_teacher_sprites(project_root)

        # 使用粗體微軟正黑體提升考卷與小抄清晰度
        self.pil_title = load_pil_font(31, bold=True)
        self.pil_q = load_pil_font(33, bold=True)
        self.pil_opt = load_pil_font(28, bold=True)
        self.pil_small = load_pil_font(22, bold=True)
        self.pil_cheat_hdr = load_pil_font(22, bold=True)
        self.pil_cheat = load_pil_font(23, bold=True)

        cjk_reg = find_cjk_font_path(bold=False)
        cjk_bold = find_cjk_font_path(bold=True)
        if cjk_reg and cjk_bold:
            self.pg_xs = pygame.font.Font(cjk_reg, 14)
            self.pg_small = pygame.font.Font(cjk_bold, 16)
            self.pg_med = pygame.font.Font(cjk_bold, 20)
            self.pg_big = pygame.font.Font(cjk_bold, 26)
        else:
            fam = "microsoftjhenghei,simhei,arial"
            self.pg_xs = pygame.font.SysFont(fam, 14)
            self.pg_small = pygame.font.SysFont(fam, 16, bold=True)
            self.pg_med = pygame.font.SysFont(fam, 20, bold=True)
            self.pg_big = pygame.font.SysFont(fam, 26, bold=True)

        self.peek_side = None
        self.peek_progress = 0.0
        self.peek_unlocked = {}
        self._just_unlocked_peek = False

        # 高效髒旗標快取 (僅資料改變時才重畫 PIL 考卷與小抄)
        self._paper_hit_cache = None
        self._paper_cache_key = None
        self._paper_cached_pil = None
        self._hovered_opt = None
        self._hovered_nav = None
        self._lean_forward = False
        self._last_time = 0.0

    def _load_teacher_sprites(self, project_root):
        assets = os.path.join(project_root, "assets")
        self.teacher_sprites = {}
        mapping = {
            "back": ["teacher_back.png"],
            "peek": ["teacher_peek.png"],
            "patrol": ["teacher_patrol.png"],
            "laugh": ["teacher_laugh.png", "nailong.png", "nailong.jpg"],
        }
        for key, fnames in mapping.items():
            for fn in fnames:
                p = os.path.join(assets, fn)
                if os.path.exists(p):
                    try:
                        self.teacher_sprites[key] = pygame.image.load(p).convert_alpha()
                        break
                    except Exception:
                        pass

    def reset(self):
        self.camera.reset()
        self.peek_side = None
        self.peek_progress = 0.0
        self.peek_unlocked.clear()
        self._just_unlocked_peek = False
        self._paper_hit_cache = None
        self._paper_cache_key = None
        self._paper_cached_pil = None

    def set_viewport(self, rect):
        self.viewport_rect = rect

    def set_lean_forward(self, active):
        self._lean_forward = bool(active)

    def consume_peek_unlocked_sfx(self):
        flag = self._just_unlocked_peek
        self._just_unlocked_peek = False
        return flag

    def update(self, dt, current_q_idx, mouse_screen_pos=None):
        self._last_time += dt
        if mouse_screen_pos is not None:
            mx, my = mouse_screen_pos
            if mx <= self.viewport_rect.right + 28:
                nx = ((mx - self.viewport_rect.left) / max(1, self.viewport_rect.width)) * 2.0 - 1.0
                ny = ((my - self.viewport_rect.top) / max(1, self.viewport_rect.height)) * 2.0 - 1.0
                self.camera.set_look_target(nx, ny, lean_forward=self._lean_forward)
            elif self._lean_forward:
                self.camera.set_look_target(0.0, 0.55, lean_forward=True)
        elif self._lean_forward:
            self.camera.set_look_target(0.0, 0.55, lean_forward=True)

        self.camera.update(dt)

        side = self.camera.get_looking_neighbor_side()
        if side is not None:
            if side != self.peek_side:
                self.peek_side = side
                self.peek_progress = 0.0
            key = (current_q_idx, side)
            if key in self.peek_unlocked:
                self.peek_progress = 1.0
            else:
                self.peek_progress = min(1.0, self.peek_progress + dt / 1.35)
                if self.peek_progress >= 1.0:
                    self._just_unlocked_peek = True
        else:
            self.peek_side = None
            self.peek_progress = max(0.0, self.peek_progress - dt * 2.2)

        self._hovered_opt = None
        self._hovered_nav = None
        if mouse_screen_pos is not None:
            kind, val = self.hit_test_paper(mouse_screen_pos[0], mouse_screen_pos[1])
            if kind == "opt":
                self._hovered_opt = val
            elif kind in ("prev", "next"):
                self._hovered_nav = kind

    def hit_test_paper(self, screen_x, screen_y):
        if self._paper_hit_cache is None or not self.viewport_rect.collidepoint((screen_x, screen_y)):
            return (None, None)

        coeffs, bx, by = self._paper_hit_cache
        lx = (screen_x - self.viewport_rect.left) - bx
        ly = (screen_y - self.viewport_rect.top) - by
        a, b, c, d, e, f, g, h = coeffs
        denom = g * lx + h * ly + 1.0
        if abs(denom) < 1e-6:
            return (None, None)
        u = (a * lx + b * ly + c) / denom
        v = (d * lx + e * ly + f) / denom

        if not (0.0 <= u <= TEX_W and 0.0 <= v <= TEX_H):
            return (None, None)

        for i in range(4):
            y0 = 285 + i * 82
            y1 = y0 + 70
            if 44 <= u <= TEX_W - 44 and y0 <= v <= y1:
                return ("opt", i)

        if 622 <= v <= 682:
            if 44 <= u <= 240:
                return ("prev", None)
            if TEX_W - 240 <= u <= TEX_W - 44:
                return ("next", None)

        return (None, None)

    # ------------------------------------------------------------------
    # 主渲染管線
    # ------------------------------------------------------------------
    def render(self, surface, exam, teacher, bio_signals):
        vp = pygame.Surface((self.viewport_rect.width, self.viewport_rect.height))
        vw, vh = vp.get_size()

        self._draw_room_shell(vp, vw, vh, exam)

        # 建立 Z-Sort 3D 場景物件佇列 (講台/黑板凹槽、8 位同學 3D 桌椅與身體、走道中的奶龍老師)
        queue = SceneDrawQueue(self.camera, vw, vh)
        self._queue_blackboard_and_podium(queue, vw, vh, teacher, exam)
        self._queue_classmates_3d(queue, vw, vh, exam)
        self._queue_teacher_3d(queue, teacher)
        queue.flush(vp)

        # 鄰座標籤與偷看氣泡放在實體桌椅之上
        self._draw_neighbor_hud(vp, vw, vh, exam)

        # 主角前景 3D 課桌、道具、高清單應性考卷與抽屜小抄
        self._draw_player_desk_and_exam(vp, vw, vh, exam, bio_signals)
        self._draw_drawer_and_cheatsheet(vp, vw, vh, exam, bio_signals)
        self._draw_overlays_and_vignette(vp, vw, vh, teacher, bio_signals, exam)

        surface.blit(vp, self.viewport_rect.topleft)

    def _fast_poly(self, surf, pts_3d, color, vw, vh, border_color=None, bw=1):
        pts = []
        for x, y, z in pts_3d:
            p = self.camera.project(x, y, z, vw, vh)
            if p is None:
                return None
            pts.append((p[0], p[1]))
        pygame.draw.polygon(surf, color, pts)
        if border_color:
            pygame.draw.polygon(surf, border_color, pts, bw)
        return pts

    def _draw_room_shell(self, surf, vw, vh, exam):
        surf.fill((226, 224, 214))

        # 地板木質基色 + 木板透視條紋
        self._fast_poly(
            surf,
            [(-4.2, 0.0, -0.5), (4.2, 0.0, -0.5), (4.2, 0.0, 5.9), (-4.2, 0.0, 5.9)],
            (172, 138, 102),
            vw,
            vh,
        )
        for z_plank in (0.4, 1.1, 1.8, 2.5, 3.2, 3.9, 4.6, 5.3):
            p1 = self.camera.project(-4.1, 0.0, z_plank, vw, vh)
            p2 = self.camera.project(4.1, 0.0, z_plank, vw, vh)
            if p1 and p2:
                pygame.draw.line(surf, (148, 114, 80), (p1[0], p1[1]), (p2[0], p2[1]), 1)
        for x_plank in (-3.0, -1.9, -0.85, 0.85, 1.9, 3.0):
            p1 = self.camera.project(x_plank, 0.0, 0.0, vw, vh)
            p2 = self.camera.project(x_plank, 0.0, 5.8, vw, vh)
            if p1 and p2:
                pygame.draw.line(surf, (152, 118, 84), (p1[0], p1[1]), (p2[0], p2[1]), 1)

        # 左牆外陽光斜射光影
        for wz in (1.1, 3.1):
            self._fast_poly(
                surf,
                [(-3.4, 0.005, wz), (-0.4, 0.005, wz + 0.15), (-0.4, 0.005, wz + 1.35), (-3.4, 0.005, wz + 1.2)],
                (198, 170, 132),
                vw,
                vh,
            )

        # 後牆 (講台後方) + 腰帶護牆板
        self._fast_poly(surf, [(-4.2, 0.95, 5.85), (4.2, 0.95, 5.85), (4.2, 3.4, 5.85), (-4.2, 3.4, 5.85)], (236, 232, 220), vw, vh)
        self._fast_poly(surf, [(-4.2, 0.0, 5.85), (4.2, 0.0, 5.85), (4.2, 0.95, 5.85), (-4.2, 0.95, 5.85)], (188, 198, 186), vw, vh, (150, 160, 148), 2)

        # 左右側牆與踢腳板
        self._fast_poly(surf, [(-3.8, 0.95, -0.5), (-3.8, 0.95, 5.85), (-3.8, 3.4, 5.85), (-3.8, 3.4, -0.5)], (220, 228, 234), vw, vh)
        self._fast_poly(surf, [(-3.8, 0.0, -0.5), (-3.8, 0.0, 5.85), (-3.8, 0.95, 5.85), (-3.8, 0.95, -0.5)], (178, 190, 182), vw, vh, (145, 156, 148), 2)

        self._fast_poly(surf, [(3.8, 0.95, -0.5), (3.8, 0.95, 5.85), (3.8, 3.4, 5.85), (3.8, 3.4, -0.5)], (224, 220, 208), vw, vh)
        self._fast_poly(surf, [(3.8, 0.0, -0.5), (3.8, 0.0, 5.85), (3.8, 0.95, 5.85), (3.8, 0.95, -0.5)], (184, 188, 174), vw, vh, (148, 152, 138), 2)

        # 右牆佈告欄 & 考場守則海報
        self._fast_poly(surf, [(3.78, 1.32, 1.8), (3.78, 1.32, 3.4), (3.78, 2.38, 3.4), (3.78, 2.38, 1.8)], (176, 126, 74), vw, vh, (112, 78, 42), 2)
        self._fast_poly(surf, [(3.76, 1.42, 1.95), (3.76, 1.42, 2.60), (3.76, 2.28, 2.60), (3.76, 2.28, 1.95)], (248, 238, 195), vw, vh)
        self._fast_poly(surf, [(3.76, 1.42, 2.70), (3.76, 1.42, 3.25), (3.76, 2.28, 3.25), (3.76, 2.28, 2.70)], (210, 234, 248), vw, vh)

        # 左牆 3 扇立體窗戶 + 外頭藍天綠樹 + 窗框分隔
        for wz in (0.65, 2.25, 3.85):
            self._fast_poly(surf, [(-3.78, 1.05, wz), (-3.78, 1.05, wz + 1.25), (-3.78, 2.60, wz + 1.25), (-3.78, 2.60, wz)], (162, 214, 248), vw, vh, (95, 108, 122), 3)
            # 窗外遠山綠樹剪影
            self._fast_poly(surf, [(-3.77, 1.06, wz + 0.04), (-3.77, 1.06, wz + 1.21), (-3.77, 1.48, wz + 1.02), (-3.77, 1.56, wz + 0.35)], (92, 162, 104), vw, vh)
            # 中央窗櫺與立體窗台
            p_top = self.camera.project(-3.76, 2.60, wz + 0.625, vw, vh)
            p_bot = self.camera.project(-3.76, 1.05, wz + 0.625, vw, vh)
            if p_top and p_bot:
                pygame.draw.line(surf, (105, 118, 130), (p_top[0], p_top[1]), (p_bot[0], p_bot[1]), 3)
            self._fast_poly(surf, [(-3.78, 1.02, wz - 0.04), (-3.58, 1.02, wz - 0.04), (-3.58, 1.05, wz + 1.29), (-3.78, 1.05, wz + 1.29)], (206, 178, 136), vw, vh, (130, 105, 72), 1)

        # 天花板格柵與 3 組日光燈管
        for lz in (1.4, 3.2, 4.8):
            for lx in (-1.35, 1.35):
                self._fast_poly(
                    surf,
                    [(lx - 0.55, 3.25, lz - 0.14), (lx + 0.55, 3.25, lz - 0.14), (lx + 0.55, 3.25, lz + 0.14), (lx - 0.55, 3.25, lz + 0.14)],
                    (248, 252, 255),
                    vw,
                    vh,
                    (175, 185, 200),
                    2,
                )

    def _queue_blackboard_and_podium(self, q, vw, vh, teacher, exam):
        # 立體黑板框 & 綠板面 & 底部粉筆槽
        q.push_box(-2.45, 1.04, 5.72, 2.45, 2.62, 5.84, (138, 92, 50), border_rgb=(85, 55, 28))
        q.push_poly(
            [(-2.34, 1.12, 5.71), (2.34, 1.12, 5.71), (2.34, 2.54, 5.71), (-2.34, 2.54, 5.71)],
            (28, 76, 48),
            normal=(0, 0, -1),
            border_rgb=(18, 48, 30),
            border_w=2,
            shade=False,
        )
        # 立體粉筆槽 + 粉筆棒
        q.push_box(-2.30, 1.00, 5.56, 2.30, 1.08, 5.72, (165, 118, 68), border_rgb=(105, 70, 38))
        q.push_box(-0.55, 1.08, 5.59, -0.35, 1.12, 5.66, (245, 245, 245))
        q.push_box(-0.28, 1.08, 5.59, -0.10, 1.12, 5.66, (250, 215, 85))
        q.push_box(0.25, 1.08, 5.58, 0.48, 1.15, 5.69, (55, 65, 90))  # 板擦

        # 動態黑板板書文字與掛鐘
        def _draw_board_details(surf, _proj):
            mid = self.camera.project(0.0, 1.92, 5.70, vw, vh)
            sub = self.camera.project(0.0, 1.56, 5.70, vw, vh)
            clk = self.camera.project(2.78, 2.52, 5.78, vw, vh)
            if mid:
                btxt = "生醫電子學期末考 [嚴禁左顧右盼]"
                if teacher.rush_mode:
                    btxt = "最後 28 秒！再亂動就當場死當！"
                elif teacher.is_close_aisle():
                    btxt = "注意！老師已走近走道巡邏！"
                s1 = self.pg_med.render(btxt, True, (236, 248, 232))
                surf.blit(s1, (mid[0] - s1.get_width() // 2, mid[1] - s1.get_height() // 2))
            if sub:
                eq = self.pg_xs.render("f_c = 1 / (2πRC)   |   AD620: G = 1 + 49.4k/Rg   |   fs >= 2 f_max", True, (188, 222, 195))
                surf.blit(eq, (sub[0] - eq.get_width() // 2, sub[1] - eq.get_height() // 2))
            if clk:
                r = max(14, int(135.0 / max(1.0, clk[2])))
                cx, cy = int(clk[0]), int(clk[1])
                pygame.draw.circle(surf, (45, 52, 68), (cx, cy), r + 3)
                pygame.draw.circle(surf, (246, 248, 252), (cx, cy), r)
                ang = (exam.time_remaining / max(1.0, exam.exam_time)) * 2.0 * math.pi - math.pi * 0.5
                pygame.draw.line(surf, (220, 45, 45), (cx, cy), (cx + math.cos(ang) * r * 0.78, cy + math.sin(ang) * r * 0.78), 2)
                pygame.draw.line(surf, (30, 35, 48), (cx, cy), (cx, cy - r * 0.48), 2)

        q.push_custom(0.0, 1.92, 5.70, _draw_board_details, depth_bias=-0.02)

        # 講台講桌置於右側 (x=+0.95, z=4.95)，中央走道完全淨空！
        px0, px1, pz0, pz1 = 0.62, 1.68, 4.65, 5.28
        q.push_box(px0, 0.0, pz0, px1, 0.92, pz1, (152, 102, 62), border_rgb=(92, 60, 34))
        q.push_box(px0 - 0.04, 0.92, pz0 - 0.04, px1 + 0.04, 0.98, pz1 + 0.04, (186, 132, 82), border_rgb=(110, 74, 42))
        # 講桌上的 3D 筆電與一疊空白考卷
        q.push_box(0.84, 0.98, 4.78, 1.24, 1.02, 5.04, (65, 72, 86))
        q.push_poly(
            [(0.85, 1.02, 5.03), (1.23, 1.02, 5.03), (1.23, 1.28, 5.10), (0.85, 1.28, 5.10)],
            (85, 145, 220),
            normal=(0, 0.2, -1),
            border_rgb=(45, 52, 64),
            border_w=2,
        )
        q.push_box(1.34, 0.98, 4.82, 1.58, 1.05, 5.08, (245, 245, 240), border_rgb=(195, 195, 190))

    def _queue_classmates_3d(self, q, vw, vh, exam):
        for wx, wz, name, _role, shirt_rgb in self.CLASSMATES:
            # 1. 學生課桌 (desktop + cubby + 4 dark steel legs + exam paper + pencil box)
            q.push_box(wx - 0.36, 0.68, wz - 0.24, wx + 0.36, 0.72, wz + 0.26, (206, 158, 104), border_rgb=(128, 92, 54))
            q.push_box(wx - 0.31, 0.54, wz - 0.19, wx + 0.31, 0.68, wz + 0.21, (162, 120, 76), border_rgb=(105, 74, 42))
            for lx in (wx - 0.32, wx + 0.28):
                for lz in (wz - 0.20, wz + 0.20):
                    q.push_box(lx, 0.0, lz, lx + 0.04, 0.68, lz + 0.04, (58, 64, 74))
            # 桌上的白考卷與藍鉛筆盒
            q.push_poly(
                [(wx - 0.18, 0.724, wz - 0.14), (wx + 0.18, 0.724, wz - 0.14), (wx + 0.18, 0.724, wz + 0.16), (wx - 0.18, 0.724, wz + 0.16)],
                (248, 248, 242),
                normal=(0, 1, 0),
                border_rgb=(190, 192, 186),
                depth_bias=-0.01,
            )
            q.push_box(wx + 0.20, 0.72, wz + 0.05, wx + 0.30, 0.76, wz + 0.21, (65, 130, 205))

            # 2. 學生座椅 (坐墊 + 椅背 + 椅腳)
            cz_seat = wz - 0.38
            q.push_box(wx - 0.20, 0.41, cz_seat - 0.16, wx + 0.20, 0.45, cz_seat + 0.16, (175, 130, 84))
            q.push_box(wx - 0.20, 0.45, cz_seat - 0.17, wx + 0.20, 0.80, cz_seat - 0.13, (162, 118, 72), border_rgb=(105, 74, 42))
            for lx in (wx - 0.18, wx + 0.15):
                q.push_box(lx, 0.0, cz_seat - 0.14, lx + 0.03, 0.42, cz_seat - 0.11, (54, 60, 68))

            # 3. 低多邊形 3D 學生角色 (身軀 + 雙前臂 + 頭顱 + 頭髮蓋)
            sz_body = cz_seat + 0.03
            q.push_box(wx - 0.20, 0.45, sz_body - 0.10, wx + 0.20, 0.96, sz_body + 0.10, shirt_rgb, border_rgb=(45, 55, 72))
            # 雙手肘伏在桌面作答 (微動)
            arm_jig = math.sin(self._last_time * (5.5 if name == "小華" else 2.2) + wx) * 0.018
            q.push_box(wx - 0.23, 0.72, wz - 0.15, wx - 0.13, 0.79, sz_body + 0.04, (238, 196, 165))
            q.push_box(wx + 0.10 + arm_jig, 0.72, wz - 0.15, wx + 0.21 + arm_jig, 0.79, sz_body + 0.04, (238, 196, 165))
            # 頭與深色髮頂
            q.push_box(wx - 0.11, 0.97, sz_body - 0.09, wx + 0.11, 1.19, sz_body + 0.09, (242, 200, 168), border_rgb=(140, 108, 86))
            q.push_box(wx - 0.12, 1.13, sz_body - 0.10, wx + 0.12, 1.24, sz_body + 0.10, (44, 38, 36))

    def _queue_teacher_3d(self, q, teacher):
        """將多表情 3D 去背奶龍監考官置入 3D 空間 Z-Sort 佇列，隨走道距離縮放與踩地陰影。"""
        tx = teacher.pos_x
        tz = teacher.pos_z
        bob_y = abs(math.sin(teacher.walk_phase)) * 0.045 if abs(teacher.target_z - tz) > 0.08 else 0.0

        def _draw_teacher_billboard(surf, _proj):
            vw, vh = surf.get_size()
            feet_p = self.camera.project(tx, 0.0 + bob_y, tz, vw, vh)
            head_p = self.camera.project(tx, 1.56 + bob_y, tz, vw, vh)
            shadow_l = self.camera.project(tx - 0.42, 0.01, tz, vw, vh)
            shadow_r = self.camera.project(tx + 0.42, 0.01, tz, vw, vh)
            if not feet_p or not head_p:
                return

            # 地板接觸橢圓陰影
            if shadow_l and shadow_r:
                sw = max(24, int(abs(shadow_r[0] - shadow_l[0])))
                sh = max(8, int(sw * 0.26))
                sh_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
                pygame.draw.ellipse(sh_surf, (20, 18, 14, 105), (0, 0, sw, sh))
                surf.blit(sh_surf, (int(feet_p[0] - sw // 2), int(feet_p[1] - sh // 2)))

            cx = int(feet_p[0])
            h_px = max(75, int(abs(feet_p[1] - head_p[1])))
            top_y = int(head_p[1])

            # 根據監考狀態挑選對應 3D 渲染立繪 (大笑 / 巡堂 / 回頭偷瞄 / 背對板書)
            if teacher.busted and "laugh" in self.teacher_sprites:
                sprite_key = "laugh"
                h_px = int(h_px * 1.06)
            elif teacher.head_angle >= 125.0 and "patrol" in self.teacher_sprites:
                sprite_key = "patrol"
            elif teacher.head_angle >= 20.0 and "peek" in self.teacher_sprites:
                sprite_key = "peek"
            elif "back" in self.teacher_sprites:
                sprite_key = "back"
            else:
                sprite_key = None

            if sprite_key:
                base_spr = self.teacher_sprites[sprite_key]
                aspect = base_spr.get_width() / max(1, base_spr.get_height())
                w_px = max(40, int(h_px * aspect))
                scaled = pygame.transform.smoothscale(base_spr, (w_px, h_px))
                surf.blit(scaled, (cx - w_px // 2, top_y))

                # 危險逼近紅光邊框暗示
                if teacher.is_close_aisle() and teacher.is_facing_player():
                    pulse = int(abs(math.sin(self._last_time * 9.0)) * 3 + 2)
                    pygame.draw.circle(surf, (255, 55, 55), (cx, top_y - 16), 9 + pulse, 3)

            # 頭頂即時警戒標籤 + 逼近距離提示
            if teacher.distracted_timer > 0.0:
                tag = self.pg_small.render("? 分心中 ?", True, (65, 165, 255))
                bg_c = (15, 32, 56)
            elif teacher.busted:
                tag = self.pg_med.render("抓到了哈哈哈哈哈！", True, (255, 95, 95))
                bg_c = (48, 12, 16)
            elif teacher.is_facing_player():
                dist_tag = f" [走道逼近 {tz:.1f}m!]" if tz < 3.6 else ""
                tag = self.pg_med.render(f"! 巡視中{dist_tag} !", True, (255, 80, 80))
                bg_c = (45, 16, 20)
            elif teacher.state.name in ("BUZZER_WARNING", "SILENT_PEEK"):
                tag = self.pg_med.render("!! 準備回頭 !!", True, (255, 195, 65))
                bg_c = (42, 30, 12)
            else:
                tag = None
                bg_c = (20, 24, 34)

            if tag:
                tw, th = tag.get_width(), tag.get_height()
                py = max(58, top_y - th - 14)
                pill = pygame.Rect(cx - tw // 2 - 10, py, tw + 20, th + 6)
                pygame.draw.rect(surf, bg_c, pill, border_radius=8)
                pygame.draw.rect(surf, (255, 255, 255), pill, 1, border_radius=8)
                surf.blit(tag, (pill.x + 10, pill.y + 3))

        q.push_custom(tx, 0.75, tz, _draw_teacher_billboard)

    def _draw_neighbor_hud(self, surf, vw, vh, exam):
        for wx, wz, name, role, _col in self.CLASSMATES[:2]:
            side = "left" if wx < 0 else "right"
            head_p = self.camera.project(wx, 1.32, wz - 0.35, vw, vh)
            desk_p = self.camera.project(wx, 0.85, wz, vw, vh)
            if not head_p:
                continue
            bx, by, _ = head_p
            label_col = (255, 232, 120) if role == "電資學霸" else (205, 224, 244)
            tag = self.pg_small.render(f"{name} ({role})", True, label_col)
            bg = pygame.Rect(int(bx - tag.get_width() // 2 - 8), int(by - 26), tag.get_width() + 16, tag.get_height() + 6)
            pygame.draw.rect(surf, (20, 26, 38), bg, border_radius=6)
            pygame.draw.rect(surf, (70, 95, 130), bg, 1, border_radius=6)
            surf.blit(tag, (bg.x + 8, bg.y + 3))

            if not desk_p:
                continue
            q_idx = exam.current_q_idx
            key = (q_idx, side)
            if key in self.peek_unlocked:
                ans_char, _lbl = self.peek_unlocked[key]
                pop = self.pg_med.render(f"Q{q_idx + 1} 偷看到: [ {ans_char} ]", True, (95, 255, 165))
                pbg = pygame.Rect(int(desk_p[0] - pop.get_width() // 2 - 10), int(desk_p[1] - 32), pop.get_width() + 20, pop.get_height() + 8)
                pygame.draw.rect(surf, (14, 42, 30), pbg, border_radius=8)
                pygame.draw.rect(surf, (80, 235, 145), pbg, 2, border_radius=8)
                surf.blit(pop, (pbg.x + 10, pbg.y + 4))
            elif self.peek_side == side and self.peek_progress > 0.05:
                if not exam.is_neighbor_ready(side, q_idx):
                    wait_txt = self.pg_small.render(f"{name} 還在寫前面題目...", True, (255, 195, 95))
                    wbg = pygame.Rect(int(desk_p[0] - wait_txt.get_width() // 2 - 8), int(desk_p[1] - 26), wait_txt.get_width() + 16, wait_txt.get_height() + 6)
                    pygame.draw.rect(surf, (38, 28, 18), wbg, border_radius=6)
                    surf.blit(wait_txt, (wbg.x + 8, wbg.y + 3))
                    self.peek_progress = 0.0
                elif self.peek_progress >= 0.99:
                    letter, note_lbl = exam.get_neighbor_guess(side, q_idx)
                    self.peek_unlocked[key] = (letter, note_lbl)
                    exam.mark_cheated_current()
                else:
                    cx_d, cy_d = int(desk_p[0]), int(desk_p[1] - 12)
                    pygame.draw.circle(surf, (24, 30, 42), (cx_d, cy_d), 20)
                    pygame.draw.arc(
                        surf,
                        (95, 220, 255),
                        (cx_d - 18, cy_d - 18, 36, 36),
                        -math.pi * 0.5,
                        -math.pi * 0.5 + 2.0 * math.pi * self.peek_progress,
                        4,
                    )

    def _draw_player_desk_and_exam(self, surf, vw, vh, exam, bio_signals):
        # 主角實木桌面 (具備前後立體厚度與金屬邊框)
        self._fast_poly(surf, [(-0.62, 0.67, 0.10), (0.62, 0.67, 0.10), (0.62, 0.72, 0.10), (-0.62, 0.72, 0.10)], (146, 102, 58), vw, vh, (95, 65, 34), 2)
        self._fast_poly(surf, [(-0.62, 0.72, 0.10), (0.62, 0.72, 0.10), (0.62, 0.72, 0.80), (-0.62, 0.72, 0.80)], (206, 158, 100), vw, vh, (125, 88, 48), 2)

        # 桌上立體文具道具 (右側藍色橡皮擦 + 木鉛筆 + 左上准考證)
        self._fast_poly(surf, [(0.42, 0.724, 0.30), (0.49, 0.724, 0.30), (0.49, 0.724, 0.40), (0.42, 0.724, 0.40)], (245, 248, 252), vw, vh, (65, 115, 200), 2)
        self._fast_poly(surf, [(0.42, 0.724, 0.30), (0.49, 0.724, 0.30), (0.49, 0.742, 0.30), (0.42, 0.742, 0.30)], (55, 110, 195), vw, vh)
        # 2B 鉛筆
        self._fast_poly(surf, [(0.41, 0.726, 0.45), (0.43, 0.726, 0.45), (0.47, 0.726, 0.68), (0.45, 0.726, 0.68)], (245, 188, 52), vw, vh, (140, 95, 25), 1)
        # 左側學生證
        self._fast_poly(surf, [(-0.56, 0.724, 0.44), (-0.42, 0.724, 0.44), (-0.42, 0.724, 0.62), (-0.56, 0.724, 0.62)], (232, 242, 252), vw, vh, (110, 145, 185), 2)

        # 考卷 3D 貼圖四角（放置於桌面中央靠前一點，確保所有選項與底欄完整落在視野內）
        paper_3d = [
            (-0.38, 0.726, 0.76),
            (0.38, 0.726, 0.76),
            (0.36, 0.726, 0.20),
            (-0.36, 0.726, 0.20),
        ]
        projected = [self.camera.project(x, y, z, vw, vh) for (x, y, z) in paper_3d]
        if any(p is None for p in projected):
            self._paper_hit_cache = None
            return

        screen_quad = [(p[0], p[1]) for p in projected]
        min_x = int(math.floor(min(p[0] for p in screen_quad)))
        max_x = int(math.ceil(max(p[0] for p in screen_quad)))
        min_y = int(math.floor(min(p[1] for p in screen_quad)))
        max_y = int(math.ceil(max(p[1] for p in screen_quad)))
        bw = max_x - min_x
        bh = max_y - min_y
        if bw < 24 or bh < 24 or bw > vw * 2 or bh > vh * 2:
            self._paper_hit_cache = None
            return

        local_quad = [(x - min_x, y - min_y) for (x, y) in screen_quad]
        tex_quad = [(0.0, 0.0), (float(TEX_W), 0.0), (float(TEX_W), float(TEX_H)), (0.0, float(TEX_H))]
        coeffs = solve_perspective_coeffs(local_quad, tex_quad)
        if coeffs is None:
            self._paper_hit_cache = None
            return

        self._paper_hit_cache = (coeffs, min_x, min_y)

        # 使用高解析髒旗標快取 + BICUBIC 反鋸齒銳利透視變換
        stroop = bio_signals.get_stroop_overload()
        stroop_frame = int(self._last_time * 4.0) if stroop > 0.25 else 0
        cache_key = (
            exam.current_q_idx,
            exam.user_answers[exam.current_q_idx],
            self._hovered_opt,
            self._hovered_nav,
            int(exam.time_remaining * 2.0),
            int(stroop * 10),
            stroop_frame,
        )
        if cache_key != self._paper_cache_key or self._paper_cached_pil is None:
            self._paper_cached_pil = self._render_exam_texture(exam, bio_signals)
            self._paper_cache_key = cache_key

        warped = self._paper_cached_pil.transform(
            (bw, bh),
            Image.Transform.PERSPECTIVE,
            coeffs,
            Image.Resampling.BICUBIC,
        )
        pg_paper = pygame.image.frombuffer(warped.tobytes(), (bw, bh), "RGBA")
        surf.blit(pg_paper, (min_x, min_y))

    def _render_exam_texture(self, exam, bio_signals):
        img = Image.new("RGBA", (TEX_W, TEX_H), (255, 253, 246, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle((6, 6, TEX_W - 7, TEX_H - 7), outline=(65, 76, 98, 255), width=4)

        q = exam.get_current_question()
        chosen = exam.user_answers[exam.current_q_idx]
        stroop = bio_signals.get_stroop_overload()

        # 標題欄
        header = f"生醫電子期末考 | 第 {exam.current_q_idx + 1}/10 題  (進度 {exam.get_progress_str()})"
        draw.text((40, 22), header, fill=(22, 42, 88, 255), font=self.pil_title)
        t_col = (210, 32, 32, 255) if exam.time_remaining <= 28.0 else (28, 108, 56, 255)
        draw.text((TEX_W - 235, 22), f"剩餘 {exam.time_remaining:05.1f}s", fill=t_col, font=self.pil_title)
        draw.line((34, 72, TEX_W - 34, 72), fill=(115, 130, 155, 255), width=3)

        # 題幹粗體大字
        lines = wrap_text_lines(q.prompt, self.pil_q, draw, TEX_W - 84)
        y_cursor = 88
        for line in lines[:4]:
            jx = int(math.sin(self._last_time * 18.0 + y_cursor) * 4.0 * stroop) if stroop > 0.25 else 0
            draw.text((44 + jx, y_cursor), line, fill=(12, 16, 22, 255), font=self.pil_q)
            y_cursor += 44

        # 4 個選項卡片 (高對比大字)
        stroop_colors = [
            (205, 30, 40, 255),
            (28, 105, 215, 255),
            (22, 145, 58, 255),
            (185, 88, 15, 255),
        ]
        for i, opt_text in enumerate(q.options):
            oy = 285 + i * 82
            rect = (44, oy, TEX_W - 44, oy + 70)
            is_chosen = chosen == i
            is_hover = self._hovered_opt == i

            if is_chosen:
                fill_c = (205, 230, 255, 255)
                out_c = (26, 98, 210, 255)
                w = 4
            elif is_hover:
                fill_c = (234, 243, 254, 255)
                out_c = (95, 132, 185, 255)
                w = 3
            else:
                fill_c = (247, 245, 236, 255)
                out_c = (158, 162, 158, 255)
                w = 2

            draw.rounded_rectangle(rect, radius=12, fill=fill_c, outline=out_c, width=w)
            label = f"({chr(65 + i)})  {opt_text}"
            txt_c = (12, 18, 28, 255)
            ox_jit = 0
            if stroop > 0.28 and not is_chosen:
                txt_c = stroop_colors[(i + int(self._last_time * 3.8)) % 4]
                ox_jit = int(math.cos(self._last_time * 22.0 + i * 1.7) * 5.0 * stroop)
            draw.text((64 + ox_jit, oy + 17), label, fill=txt_c, font=self.pil_opt)

        # 底部導覽列（移除方框缺字符號並精準置中快捷鍵提示，絕不重疊）
        prev_bg = (220, 232, 248, 255) if self._hovered_nav == "prev" else (238, 236, 226, 255)
        next_bg = (220, 232, 248, 255) if self._hovered_nav == "next" else (238, 236, 226, 255)
        draw.rounded_rectangle((44, 622, 240, 680), radius=10, fill=prev_bg, outline=(95, 108, 132, 255), width=3)
        draw.text((66, 637), "< 上一題 [←]", fill=(25, 36, 62, 255), font=self.pil_small)

        draw.rounded_rectangle((TEX_W - 240, 622, TEX_W - 44, 680), radius=10, fill=next_bg, outline=(95, 108, 132, 255), width=3)
        draw.text((TEX_W - 216, 637), "下一題 [→] >", fill=(25, 36, 62, 255), font=self.pil_small)

        hint_bar = "1~4 作答 | 空白/右鍵 全開 | 按住 F 微縫 | V 放大"
        hbox = draw.textbbox((0, 0), hint_bar, font=self.pil_small)
        hw_txt = hbox[2] - hbox[0]
        draw.text(((TEX_W - hw_txt) // 2, 638), hint_bar, fill=(85, 92, 108, 255), font=self.pil_small)

        return img

    def _draw_drawer_and_cheatsheet(self, surf, vw, vh, exam, bio_signals):
        open_ratio = bio_signals.get_drawer_open_ratio()
        if open_ratio <= 0.04 and not bio_signals.emg_cramped:
            return

        drawer_w = int(min(640, vw * 0.72))
        max_h = 265
        # 微開 (<0.56) 時故意只拉出一條窄縫 (~108px)，無法看全 5 行，強化握力控制博弈
        if open_ratio < 0.56:
            slide_h = int(38 + (open_ratio / 0.56) * 78)
        else:
            slide_h = int(116 + ((open_ratio - 0.56) / 0.44) * (max_h - 116))

        cx = vw // 2
        shake_x = 0
        shake_y = 0
        if bio_signals.emg_fatigue > 60.0 and not bio_signals.emg_cramped:
            amp = int(2 + (bio_signals.emg_fatigue - 60.0) / 7.5)
            shake_x = random.randint(-amp, amp)
            shake_y = random.randint(-amp // 2, amp // 2)

        if bio_signals.emg_cramped:
            warn_w = 390
            warn_rect = pygame.Rect(cx - warn_w // 2, vh - 62, warn_w, 48)
            pygame.draw.rect(surf, (135, 24, 24), warn_rect, border_radius=10)
            pygame.draw.rect(surf, (255, 115, 95), warn_rect, 2, border_radius=10)
            t = self.pg_med.render("肌肉疲勞抽筋！抽屜強制彈回鎖定中", True, (255, 240, 225))
            surf.blit(t, (cx - t.get_width() // 2, vh - 51))
            return

        dx0 = cx - drawer_w // 2 + shake_x
        dy0 = vh - slide_h + shake_y

        # 立體木製抽屜外殼與金屬導軌
        drawer_rect = pygame.Rect(dx0, dy0, drawer_w, slide_h + 26)
        pygame.draw.rect(surf, (118, 78, 44), drawer_rect, border_top_left_radius=12, border_top_right_radius=12)
        pygame.draw.rect(surf, (62, 40, 20), drawer_rect, 4, border_top_left_radius=12, border_top_right_radius=12)
        pygame.draw.rect(surf, (145, 100, 58), (dx0 + 10, dy0 + 6, drawer_w - 20, 10), border_radius=4)

        # 立體手掌抓握抽屜前沿
        for hx in (dx0 + 20, dx0 + drawer_w - 78):
            pygame.draw.ellipse(surf, (215, 168, 134), (hx, dy0 - 9, 58, 28))
            pygame.draw.ellipse(surf, (242, 202, 170), (hx + 4, dy0 - 7, 50, 22))

        alpha, blur_r, focus_pct, _stroop_pct = bio_signals.get_cheat_opacity_and_blur()
        page_idx = bio_signals.cheat_page
        lines = exam.get_cheat_page_lines(page_idx)

        note_w = drawer_w - 48
        note_h = max_h - 30
        note_pil = Image.new("RGBA", (note_w, note_h), (255, 250, 202, 255))
        ndraw = ImageDraw.Draw(note_pil)
        ndraw.rectangle((3, 3, note_w - 4, note_h - 4), outline=(175, 152, 88, 255), width=3)

        mode_tag = "微縫僅見前半" if open_ratio < 0.56 else "抽屜全開"
        hdr = f"公式小抄 [第 {page_idx + 1}/2 頁] ({mode_tag} | Tab / 雙眨眼翻頁)"
        ndraw.text((16, 10), hdr, fill=(145, 36, 28, 255), font=self.pil_cheat_hdr)
        ndraw.line((14, 40, note_w - 14, 40), fill=(210, 190, 130, 255), width=2)

        y = 50
        for line in lines:
            ndraw.line((14, y + 31, note_w - 14, y + 31), fill=(232, 224, 175, 255), width=1)
            ndraw.text((18, y), line, fill=(18, 28, 68, 255), font=self.pil_cheat)
            y += 35

        if blur_r > 0.25:
            note_pil = note_pil.filter(ImageFilter.GaussianBlur(radius=blur_r))

        pg_note = pygame.image.frombuffer(note_pil.tobytes(), (note_w, note_h), "RGBA")
        pg_note.set_alpha(alpha)

        clip_h = max(0, min(note_h, slide_h - 16))
        if clip_h > 4:
            surf.blit(pg_note, (dx0 + 24, dy0 + 18), area=pygame.Rect(0, 0, note_w, clip_h))

        if focus_pct < 52.0 and clip_h > 36:
            fog_txt = self.pg_small.render(
                f"注意力偏低 ({focus_pct:.0f}%) 小抄模糊！按 R / E 集中精神", True, (255, 115, 115)
            )
            surf.blit(fog_txt, (cx - fog_txt.get_width() // 2, dy0 + 22))

    def _draw_overlays_and_vignette(self, surf, vw, vh, teacher, bio_signals, exam):
        if bio_signals.calm_aura > 0.08:
            aura_a = int(100 * bio_signals.calm_aura)
            aura_surf = pygame.Surface((vw, 48), pygame.SRCALPHA)
            pygame.draw.rect(aura_surf, (55, 225, 185, aura_a), (0, 0, vw, 48))
            surf.blit(aura_surf, (0, vh - 48))
            lbl = self.pg_small.render("深呼吸鎮定生效：心跳、懷疑值與專注力正在回穩", True, (225, 255, 245))
            surf.blit(lbl, (16, vh - 33))

        danger = max(teacher.suspicion / 100.0, bio_signals.get_stroop_overload() * 0.72)
        if danger > 0.45:
            a = int(min(135, (danger - 0.45) * 220))
            edge = pygame.Surface((vw, vh), pygame.SRCALPHA)
            pygame.draw.rect(edge, (225, 28, 28, a), (0, 0, vw, vh), width=18)
            surf.blit(edge, (0, 0))

        banner_bg = pygame.Surface((vw - 24, 40), pygame.SRCALPHA)
        pygame.draw.rect(banner_bg, (14, 18, 28, 215), (0, 0, vw - 24, 40), border_radius=8)
        surf.blit(banner_bg, (12, 10))
        btxt = self.pg_med.render(teacher.status_banner, True, teacher.banner_color)
        surf.blit(btxt, (vw // 2 - btxt.get_width() // 2, 16))

        if teacher.distracted_timer > 0.0 and teacher.distraction_banner:
            dtxt = self.pg_small.render(teacher.distraction_banner, True, (115, 220, 255))
            dbg = pygame.Surface((dtxt.get_width() + 24, 28), pygame.SRCALPHA)
            pygame.draw.rect(dbg, (15, 35, 58, 225), (0, 0, dbg.get_width(), 28), border_radius=6)
            dx = vw // 2 - dbg.get_width() // 2
            surf.blit(dbg, (dx, 56))
            surf.blit(dtxt, (dx + 12, 60))
        elif exam.time_remaining <= 28.0:
            rtxt = self.pg_small.render("最後 28 秒衝刺！奶娃老師走道巡查加劇！", True, (255, 130, 100))
            surf.blit(rtxt, (vw // 2 - rtxt.get_width() // 2, 56))
