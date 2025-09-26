# files source: https://github.com/intel/metro-ai-suite/tree/refs/heads/videos/videos
for file in *.ts; do
    ffmpeg -i "$file" -c:v libx264 -c:a aac "${file%.ts}.mp4"
done
