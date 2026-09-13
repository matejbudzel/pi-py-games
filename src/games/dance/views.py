"""Pygame drawing functions with no input, audio, or state transitions."""

from __future__ import annotations

import pygame

from .assets import Assets, COVER_SIZE
from .charts import Note
from .config import APP_HEIGHT, APP_WIDTH, FOREGROUND, SETTINGS
from .gameplay import Judgement, Session
from common.performance import FrameTiming
from .songs import Song


LANE_DIRECTIONS = ("left", "down", "up", "right")
LANE_SPACING = 84
LANE_START_X = APP_WIDTH // 2 - LANE_SPACING * (len(LANE_DIRECTIONS) - 1) // 2
HEADER_HEIGHT = 92
NOTE_TRAVEL_SECONDS = 2.0
LIST_TEXT_X = 104
COVER_X = APP_WIDTH - 40 - COVER_SIZE
COVER_Y = 28
GAMEPLAY_COVER_POSITION = (16, 108)
FEEDBACK_CENTER_X = (LANE_START_X + (len(LANE_DIRECTIONS) - 1) * LANE_SPACING + 16 + APP_WIDTH) // 2
GAMEPLAY_PROGRESS_RECT = pygame.Rect(40, 16, APP_WIDTH - 80, 12)
GAMEPLAY_LANES_RECT = pygame.Rect(LANE_START_X - 28, HEADER_HEIGHT, LANE_SPACING * 3 + 56, APP_HEIGHT - HEADER_HEIGHT)
GAMEPLAY_FEEDBACK_RECT = pygame.Rect(575, 100, 170, 145)
GAMEPLAY_COUNTDOWN_RECT = pygame.Rect(APP_WIDTH // 2 - 70, APP_HEIGHT // 2 - 70, 140, 140)
COVER_FRAME_COLORS = ((70, 205, 255), (235, 95, 235), (140, 90, 255))


def render_splash(screen: pygame.Surface, assets: Assets) -> None:
    screen.blit(assets.backdrops["splash"], (0, 0))
    screen.blit(assets.rainbow_title, assets.rainbow_title.get_rect(center=(APP_WIDTH // 2, APP_HEIGHT // 2)))


def render_performance_hud(screen: pygame.Surface, assets: Assets, timing: FrameTiming) -> None:
    summary = assets.performance_font.render(f"{timing.frames_per_second:4.1f} FPS  {timing.frame_ms:05.1f} ms", False, (180, 255, 180))
    detail = assets.performance_font.render(f"i{timing.input_ms:4.1f} u{timing.update_ms:4.1f} r{timing.render_ms:4.1f} p{timing.present_ms:4.1f}", False, (180, 255, 180))
    frame = pygame.Rect(0, 0, max(summary.get_width(), detail.get_width()) + 12, summary.get_height() + detail.get_height() + 12)
    frame.bottomright = (APP_WIDTH - 12, APP_HEIGHT - 10)
    pygame.draw.rect(screen, (0, 0, 0), frame)
    pygame.draw.rect(screen, (90, 150, 90), frame, width=1)
    screen.blit(summary, (frame.x + 6, frame.y + 4))
    screen.blit(detail, (frame.x + 6, frame.y + 4 + summary.get_height()))


def render_song_list(screen: pygame.Surface, assets: Assets, songs: list[Song], selected: int, first_visible_row: int, visible_rows: int) -> None:
    screen.blit(assets.backdrops["song-list"], (0, 0))
    screen.blit(assets.rainbow_title, (40, 28))
    if not songs:
        shrug = assets.shrug_font.render(r"\_(^_^)_/", False, FOREGROUND)
        screen.blit(shrug, shrug.get_rect(center=(APP_WIDTH // 2, 240)))
        _render_exit_item(screen, assets, selected, 0, APP_HEIGHT - 70)
        return
    if selected < len(songs):
        cover = assets.cover_for(songs[selected])
        _blit_framed_cover(screen, cover, (COVER_X, COVER_Y))
    for menu_row in range(first_visible_row, first_visible_row + visible_rows):
        y = 118 + (menu_row - first_visible_row) * 44
        if menu_row < len(songs):
            song = songs[menu_row]
            color = song.focus_color if menu_row == selected else FOREGROUND
            if menu_row == selected:
                _blit_chevron(screen, assets, 64, y, color)
            title = _ellipsize(assets.list_font, song.title, COVER_X - LIST_TEXT_X - 28)
            screen.blit(assets.list_font.render(title, False, color), (LIST_TEXT_X, y))
        elif menu_row == len(songs) + 1:
            _render_exit_item(screen, assets, selected, len(songs), y)


def render_application_exit_confirmation(screen: pygame.Surface, assets: Assets, selected: bool) -> None:
    screen.blit(assets.backdrops["song-list"], (0, 0))
    screen.blit(assets.rainbow_title, (40, 28))
    message = assets.question_font.render(SETTINGS.exit_confirmation_text, False, FOREGROUND)
    screen.blit(message, message.get_rect(center=(APP_WIDTH // 2, 200)))
    render_confirmation_buttons(screen, assets, SETTINGS.exit_confirm_button, SETTINGS.exit_cancel_button, selected, 286)


def render_gameplay(screen: pygame.Surface, assets: Assets, song: Song | None, session: Session | None, audio_seconds: float, song_seconds: float, feedback: Judgement | None, feedback_until: float, glow_until: dict[str, int], now_ms: int) -> None:
    if song is None:
        return
    render_gameplay_base(screen, assets, song)
    _render_gameplay_dynamic(screen, assets, session, song, audio_seconds, song_seconds, feedback, feedback_until, glow_until, now_ms)


def create_gameplay_base(screen: pygame.Surface, assets: Assets, song: Song) -> pygame.Surface:
    """Build the parts of gameplay that do not change while a song is playing."""
    base = screen.copy()
    base.fill((0, 0, 0))
    render_gameplay_base(base, assets, song)
    return base


def render_gameplay_base(screen: pygame.Surface, assets: Assets, song: Song) -> None:
    screen.blit(assets.backdrops["gameplay"], (0, 0))
    _render_gameplay_header_static(screen, assets, song)
    _blit_framed_cover(screen, assets.cover_for(song), GAMEPLAY_COVER_POSITION)
    for index, direction in enumerate(LANE_DIRECTIONS):
        center = (LANE_START_X + index * LANE_SPACING, 132)
        receptor = assets.receptors[direction]
        screen.blit(receptor, receptor.get_rect(center=center))


def render_difficulty_selection(screen: pygame.Surface, assets: Assets, song: Song | None, count: int, selected: int) -> None:
    if song is None or count == 0:
        return
    screen.blit(assets.backdrops["gameplay"], (0, 0))
    _render_gameplay_header_static(screen, assets, song)
    _blit_framed_cover(screen, assets.cover_for(song), GAMEPLAY_COVER_POSITION)
    # A sliding row keeps even files with many edit charts readable.
    visible = min(count, 6)
    first = max(0, min(selected - visible // 2, count - visible))
    left, width = GAMEPLAY_LANES_RECT.x, GAMEPLAY_LANES_RECT.width
    spacing = min(84, width // visible)
    start_x = left + (width - spacing * (visible - 1)) // 2
    for slot, index in enumerate(range(first, first + visible)):
        x = start_x + slot * spacing
        color = song.focus_color if index == selected else (145, 145, 155)
        bars = index + 1
        bar_step = min(10, 72 / bars)
        for bar in range(bars):
            y = round(162 - bar * bar_step)
            pygame.draw.rect(screen, color, (x - 20, y, 40, max(1, round(bar_step * 0.65))))
        if index == selected:
            pygame.draw.lines(screen, color, False, [(x - 10, 192), (x, 182), (x + 10, 192)], 4)
    if first > 0:
        pygame.draw.polygon(screen, FOREGROUND, [(left - 12, 136), (left - 4, 130), (left - 4, 142)])
    if first + visible < count:
        pygame.draw.polygon(screen, FOREGROUND, [(APP_WIDTH - 8, 136), (APP_WIDTH - 16, 130), (APP_WIDTH - 16, 142)])


def render_cached_gameplay(screen: pygame.Surface, base: pygame.Surface, assets: Assets, song: Song, session: Session | None, audio_seconds: float, song_seconds: float, feedback: Judgement | None, feedback_until: float, glow_until: dict[str, int], now_ms: int, countdown: int | None, previous_rectangles: list[pygame.Rect]) -> tuple[list[pygame.Rect], list[pygame.Rect]]:
    """Restore only former/current moving artwork, then paint live gameplay."""
    current_rectangles = _gameplay_dynamic_rectangles(assets, session, song_seconds, feedback, feedback_until, glow_until, now_ms, countdown)
    restored_rectangles = _merge_rectangles(previous_rectangles + current_rectangles)
    for rect in restored_rectangles:
        screen.blit(base, rect.topleft, rect)
    _render_gameplay_dynamic(screen, assets, session, song, audio_seconds, song_seconds, feedback, feedback_until, glow_until, now_ms)
    if countdown is not None:
        render_countdown(screen, assets, countdown)
    return current_rectangles, restored_rectangles


def _render_gameplay_dynamic(screen: pygame.Surface, assets: Assets, session: Session | None, song: Song, audio_seconds: float, song_seconds: float, feedback: Judgement | None, feedback_until: float, glow_until: dict[str, int], now_ms: int) -> None:
    _render_gameplay_progress(screen, song, audio_seconds)
    _render_flowing_notes(screen, assets, session, song_seconds)
    for index, direction in enumerate(LANE_DIRECTIONS):
        center = (LANE_START_X + index * LANE_SPACING, 132)
        glowing = now_ms <= glow_until[direction]
        if glowing:
            glow = assets.receptor_glows[direction]
            screen.blit(glow, glow.get_rect(center=center))
        receptor = assets.receptors[direction]
        screen.blit(receptor, receptor.get_rect(center=center))
    if feedback is not None and song_seconds <= feedback_until:
        screen.blit(assets.feedback_patches[feedback], GAMEPLAY_FEEDBACK_RECT.topleft)


def render_countdown(screen: pygame.Surface, assets: Assets, remaining: int) -> None:
    number = assets.question_font.render(str(remaining), False, FOREGROUND)
    screen.blit(number, number.get_rect(center=(APP_WIDTH // 2, APP_HEIGHT // 2)))


def render_result(screen: pygame.Surface, assets: Assets, song: Song | None, audio_seconds: float, stars: int, started_at: int, now_ms: int) -> None:
    if song is None:
        return
    screen.blit(assets.backdrops["result"], (0, 0))
    _render_gameplay_header_static(screen, assets, song)
    _render_gameplay_progress(screen, song, audio_seconds)
    star_y, star_spacing, star_start_x = 222, 40, 285
    for index in range(5):
        screen.blit(assets.draft_star, (star_start_x + index * star_spacing, star_y))
    earned_count = min(stars, (now_ms - started_at) // 500)
    for index in range(earned_count):
        screen.blit(assets.earned_star, (star_start_x + index * star_spacing, star_y))
    if earned_count >= stars and stars:
        reaction = Judgement.MISS if stars <= 2 else Judgement.OK if stars <= 4 else Judgement.GREAT
        icon = assets.feedback_icons[reaction]
        screen.blit(icon, icon.get_rect(midleft=(477, star_y + 16)))


def render_modal(screen: pygame.Surface, assets: Assets, message: str) -> None:
    dimmer = pygame.Surface((APP_WIDTH, APP_HEIGHT), pygame.SRCALPHA)
    dimmer.fill((0, 0, 0, 170))
    screen.blit(dimmer, (0, 0))
    frame = pygame.Rect(220, 162, 414, 156)
    pygame.draw.rect(screen, (20, 20, 26), frame)
    pygame.draw.rect(screen, (230, 230, 230), frame, width=3)
    text = assets.question_font.render(message, False, FOREGROUND)
    screen.blit(text, text.get_rect(center=frame.center))


def render_song_exit_confirmation(screen: pygame.Surface, assets: Assets, selected: bool) -> None:
    render_modal(screen, assets, SETTINGS.song_exit_confirmation_text)
    render_confirmation_buttons(screen, assets, SETTINGS.song_exit_confirm_button, SETTINGS.song_exit_cancel_button, selected, 270)


def render_confirmation_buttons(screen: pygame.Surface, assets: Assets, confirm: str, cancel: str, confirm_selected: bool, y: int) -> None:
    rendered = [(assets.list_font.render(label, False, (255, 150, 100) if selected else FOREGROUND), selected) for label, selected in ((confirm, confirm_selected), (cancel, not confirm_selected))]
    gap = 72
    x = (APP_WIDTH - sum(text.get_width() for text, _ in rendered) - gap) // 2
    for text, selected in rendered:
        screen.blit(text, (x, y))
        if selected:
            _blit_chevron(screen, assets, x - 34, y, (255, 150, 100))
        x += text.get_width() + gap


def _blit_framed_cover(screen: pygame.Surface, cover: pygame.Surface, position: tuple[int, int]) -> None:
    screen.blit(cover, position)
    frame = pygame.Rect(position, cover.get_size())
    for inset, color in enumerate(COVER_FRAME_COLORS):
        pygame.draw.rect(screen, color, frame.inflate(-inset * 2, -inset * 2), width=1)


def _render_gameplay_header_static(screen: pygame.Surface, assets: Assets, song: Song) -> None:
    header_color = tuple(channel * 55 // 100 for channel in song.focus_color)
    pygame.draw.rect(screen, header_color, pygame.Rect(0, 0, APP_WIDTH, HEADER_HEIGHT))
    pygame.draw.rect(screen, FOREGROUND, GAMEPLAY_PROGRESS_RECT, width=2)
    screen.blit(assets.list_font.render(song.title, False, FOREGROUND), (40, 42))


def _render_gameplay_progress(screen: pygame.Surface, song: Song, audio_seconds: float) -> None:
    ratio = min(1.0, audio_seconds / song.duration_seconds)
    if ratio > 0:
        fill = GAMEPLAY_PROGRESS_RECT.copy()
        fill.width = max(1, round(GAMEPLAY_PROGRESS_RECT.width * ratio))
        pygame.draw.rect(screen, FOREGROUND, fill)


def _render_flowing_notes(screen: pygame.Surface, assets: Assets, session: Session | None, song_seconds: float) -> None:
    if session is None:
        return
    previous_clip = screen.get_clip()
    screen.set_clip(pygame.Rect(0, HEADER_HEIGHT, APP_WIDTH, APP_HEIGHT - HEADER_HEIGHT))
    for note, active in _visible_holds(session, song_seconds):
        rectangle = _hold_rectangle(note, song_seconds, active)
        # Anchor dots to the tail so they travel with the chart, not the screen.
        tail_y = 132 + (note.end_timestamp - song_seconds) * (APP_HEIGHT + 16 - 132) / NOTE_TRAVEL_SECONDS
        _render_hold_tail(screen, assets.hold_tail, rectangle, tail_y)
        if active:
            arrow = assets.flow_arrows[note.direction]
            screen.blit(arrow, arrow.get_rect(center=(rectangle.centerx, 132)))
    has_visible_note = False
    for note in session.pending:
        if note.direction in session.active_holds and session.active_holds[note.direction].note == note:
            continue
        if note.timestamp - song_seconds > NOTE_TRAVEL_SECONDS:
            break
        seconds_until_note = note.arrow_timestamp - song_seconds
        if seconds_until_note < -0.25:
            continue
        if seconds_until_note > NOTE_TRAVEL_SECONDS:
            continue
        lane = LANE_DIRECTIONS.index(note.direction)
        y = 132 + seconds_until_note * (APP_HEIGHT + 16 - 132) / NOTE_TRAVEL_SECONDS
        if HEADER_HEIGHT <= y <= APP_HEIGHT + 16:
            arrow = assets.flow_arrows[note.direction]
            screen.blit(arrow, arrow.get_rect(center=(LANE_START_X + lane * LANE_SPACING, round(y))))
            has_visible_note = True
    if not has_visible_note and not session.active_holds:
        _render_next_note_marker(screen, session, song_seconds)
    screen.set_clip(previous_clip)


def _render_hold_tail(screen: pygame.Surface, strip: pygame.Surface, rectangle: pygame.Rect, tail_y: float) -> None:
    first = max(0, int((tail_y - APP_HEIGHT - 8) // 12))
    first_y = round(tail_y - first * 12)
    count = max(0, min(40, (first_y - rectangle.top) // 12 + 1))
    if count == 0:
        return
    height = (count - 1) * 12 + 8
    # Select the rainbow phase without changing the tail's dot spacing.
    bottom = strip.get_height() - (first % 6) * 12
    screen.blit(strip, (rectangle.centerx - 4, first_y + 4 - height),
                pygame.Rect(0, bottom - height, 8, height))


def _render_next_note_marker(screen: pygame.Surface, session: Session, song_seconds: float, next_note: Note | None = None) -> None:
    if next_note is None:
        next_note = min((note for note in session.pending if note.arrow_timestamp > song_seconds), key=lambda note: note.arrow_timestamp, default=None)
    if next_note is None:
        return
    center_x = LANE_START_X + LANE_DIRECTIONS.index(next_note.direction) * LANE_SPACING
    for offset, color in zip((-5, 0, 5), ((255, 75, 125), (255, 225, 70), (55, 225, 255))):
        pygame.draw.circle(screen, color, (center_x + offset, APP_HEIGHT - 14), 3)


def _gameplay_dynamic_rectangles(assets: Assets, session: Session | None, song_seconds: float, feedback: Judgement | None, feedback_until: float, glow_until: dict[str, int], now_ms: int, countdown: int | None) -> list[pygame.Rect]:
    rectangles = [GAMEPLAY_PROGRESS_RECT]
    rectangles.extend(_flowing_note_rectangles(assets, session, song_seconds))
    for index, direction in enumerate(LANE_DIRECTIONS):
        # Restore receptor edges before drawing their alpha pixels again.
        rectangles.append(assets.receptors[direction].get_rect(center=(LANE_START_X + index * LANE_SPACING, 132)))
        if now_ms <= glow_until[direction]:
            glow = assets.receptor_glows[direction]
            rectangles.append(glow.get_rect(center=(LANE_START_X + index * LANE_SPACING, 132)))
    if feedback is not None and song_seconds <= feedback_until:
        rectangles.append(GAMEPLAY_FEEDBACK_RECT)
    if countdown is not None:
        rectangles.append(GAMEPLAY_COUNTDOWN_RECT)
    return _merge_rectangles(rectangles)


def _flowing_note_rectangles(assets: Assets, session: Session | None, song_seconds: float) -> list[pygame.Rect]:
    if session is None:
        return []
    clip = pygame.Rect(0, HEADER_HEIGHT, APP_WIDTH, APP_HEIGHT - HEADER_HEIGHT)
    rectangles = [_hold_rectangle(note, song_seconds, active).inflate(0, 8).clip(clip) for note, active in _visible_holds(session, song_seconds)]
    for head in session.active_holds.values():
        x = LANE_START_X + LANE_DIRECTIONS.index(head.note.direction) * LANE_SPACING
        rectangles.append(assets.flow_arrows[head.note.direction].get_rect(center=(x, 132)))
    has_visible_note = False
    next_note: Note | None = None
    for note in session.pending:
        if note.direction in session.active_holds and session.active_holds[note.direction].note == note:
            continue
        if note.timestamp - song_seconds > NOTE_TRAVEL_SECONDS:
            break
        seconds_until_note = note.arrow_timestamp - song_seconds
        if seconds_until_note < -0.25:
            continue
        if seconds_until_note > NOTE_TRAVEL_SECONDS:
            continue
        lane = LANE_DIRECTIONS.index(note.direction)
        y = 132 + seconds_until_note * (APP_HEIGHT + 16 - 132) / NOTE_TRAVEL_SECONDS
        arrow = assets.flow_arrows[note.direction]
        rectangle = arrow.get_rect(center=(LANE_START_X + lane * LANE_SPACING, round(y))).clip(clip)
        if rectangle.width and rectangle.height:
            rectangles.append(rectangle)
            has_visible_note = True
    if not has_visible_note:
        if next_note is None:
            next_note = min((note for note in session.pending if note.arrow_timestamp > song_seconds), key=lambda note: note.arrow_timestamp, default=None)
        if next_note is not None:
            center_x = LANE_START_X + LANE_DIRECTIONS.index(next_note.direction) * LANE_SPACING
            rectangles.append(pygame.Rect(center_x - 8, APP_HEIGHT - 22, 16, 16))
    return rectangles


def _visible_holds(session: Session, song_seconds: float):
    for note in session.pending:
        if note.timestamp - song_seconds > NOTE_TRAVEL_SECONDS:
            break
        if note.end_timestamp is not None and note.end_timestamp >= song_seconds:
            active = note.direction in session.active_holds and session.active_holds[note.direction].note == note
            yield note, active


def _hold_rectangle(note: Note, song_seconds: float, active: bool) -> pygame.Rect:
    speed = (APP_HEIGHT + 16 - 132) / NOTE_TRAVEL_SECONDS
    x = LANE_START_X + LANE_DIRECTIONS.index(note.direction) * LANE_SPACING
    top = 132 if active else max(HEADER_HEIGHT, round(132 + (note.timestamp - song_seconds) * speed))
    bottom = min(APP_HEIGHT + 4, round(132 + (note.end_timestamp - song_seconds) * speed) + 5)
    return pygame.Rect(x - 5, top, 10, max(0, bottom - top))


def _merge_rectangles(rectangles: list[pygame.Rect]) -> list[pygame.Rect]:
    merged: list[pygame.Rect] = []
    for rectangle in rectangles:
        rectangle = rectangle.clip(pygame.Rect(0, 0, APP_WIDTH, APP_HEIGHT))
        if not rectangle.width or not rectangle.height:
            continue
        index = 0
        while index < len(merged):
            if rectangle.colliderect(merged[index]):
                rectangle = rectangle.union(merged.pop(index))
                index = 0
            else:
                index += 1
        merged.append(rectangle)
    return merged


def _render_exit_item(screen: pygame.Surface, assets: Assets, selected: int, exit_index: int, y: int) -> None:
    color = (255, 150, 100) if selected == exit_index else FOREGROUND
    if selected == exit_index:
        _blit_chevron(screen, assets, 64, y, color)
    screen.blit(assets.list_font.render(SETTINGS.exit_item_title, False, color), (LIST_TEXT_X, y))


def _blit_chevron(screen: pygame.Surface, assets: Assets, x: int, y: int, color: tuple[int, int, int]) -> None:
    screen.blit(assets.list_font.render(">", False, color), (x, y))


def _ellipsize(font: pygame.font.Font, text: str, maximum_width: int) -> str:
    if font.size(text)[0] <= maximum_width:
        return text
    suffix = "..."
    shortened = text
    while shortened and font.size(shortened + suffix)[0] > maximum_width:
        shortened = shortened[:-1]
    return shortened.rstrip() + suffix
