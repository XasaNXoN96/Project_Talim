# Demo videos

Three short MP4 files (H.264, 960x600, 7 s, no sound, no metadata) used by `manage.py seed_demo` (local development only). They are slow pans over
the drawn scenes of `apps/core/demo_art.py` and contain no real people. Regenerate with ffmpeg:

    ffmpeg -loop 1 -i scene.jpg -vf "zoompan=z='min(zoom+0.0009,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=168:s=960x600:fps=24,format=yuv420p" -t 7 -c:v libx264 -crf 30 -preset slow -movflags +faststart -an video_x.mp4
