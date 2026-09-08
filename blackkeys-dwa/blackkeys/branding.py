TONE_COLORS = {
    "light": ("text-white", "text-white/80"),
    "themed": ("text-base-content", "text-base-content/70"),
}


def WordmarkContext(
    *, tone: str, align: str, title_size: str
) -> dict[str, str]:
    title_color, subtitle_color = TONE_COLORS[tone]
    return {
        "wordmark_align_class": align,
        "wordmark_title_class": (
            f"{title_size} font-bold uppercase tracking-[0.2em] {title_color}"
        ),
        "wordmark_subtitle_class": f"text-sm font-medium {subtitle_color}",
    }
