import os
import subprocess
import json
import base64
import sys
from PIL import Image
import io
from typing import Optional

def get_total_frames(video_path):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=nb_read_frames", "-of", "default=nokey=1:noprint_wrappers=1", video_path]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    output = result.stdout.strip()
    if output.isdigit() and int(output) > 0:
        return int(output)
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames", "-of", "default=nokey=1:noprint_wrappers=1", video_path]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    output = result.stdout.strip()
    if output.isdigit() and int(output) > 0:
        return int(output)
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration,r_frame_rate", "-of", "default=nokey=1:noprint_wrappers=1", video_path]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lines = result.stdout.strip().splitlines()
    if len(lines) >= 2:
        try:
            duration = float(lines[0])
            fps_parts = lines[1].split('/')
            if len(fps_parts) == 2:
                fps = float(fps_parts[0]) / float(fps_parts[1])
            else:
                fps = float(lines[1])
            return int(duration * fps)
        except:
            pass
    return None

def optimize_image(image_data, quality=75, format="webp"):
    img = Image.open(io.BytesIO(image_data))
    output = io.BytesIO()
    
    if format == "webp":
        img.convert("RGB").save(output, format="WEBP", quality=quality, method=6)
    else:
        img.convert("RGB").save(output, format="JPEG", quality=quality, optimize=True)
    
    return output.getvalue()

def extract_frames(video_path, output_folder, step, quality=1, scale=1.0):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    scale_filter = f"scale=iw*{scale}:ih*{scale}" if scale != 1.0 else "null"
    
    ffmpeg_cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"select=not(mod(n\\,{step})),{scale_filter}",
        "-vsync", "vfr",
        "-q:v", str(quality),
        os.path.join(output_folder, "frame_%04d.jpg")
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        print(line, end='')
    proc.wait()

def create_lottie_json(frames, w, h, fps):
    precomp_layers = []
    frame_duration = 1
    
    for i in range(len(frames)):
        layer = {
            "ddd": 0,
            "ind": i + 1,
            "ty": 2,
            "nm": f"Frame {i}",
            "refId": frames[i]["id"],
            "ks": {
                "o": {"a": 0, "k": 100},
                "p": {"a": 0, "k": [w / 2, h / 2]},
                "a": {"a": 0, "k": [w / 2, h / 2]},
                "s": {"a": 0, "k": [100, 100]}
            },
            "ip": i * frame_duration,
            "op": (i + 1) * frame_duration,
            "st": i * frame_duration
        }
        precomp_layers.append(layer)

    animation_length = len(frames) * frame_duration
    
    return {
        "v": "5.5.2",
        "fr": fps,
        "ip": 0,
        "op": animation_length,
        "w": w,
        "h": h,
        "nm": "video_animation",
        "ddd": 0,
        "assets": frames,
        "layers": precomp_layers
    }

def encode_frames_to_json(frames_folder, max_frames, quality=75, format="webp"):
    files = sorted([f for f in os.listdir(frames_folder) if f.endswith(".jpg")])
    selected_files = files[:max_frames]
    frames = []
    first_frame = Image.open(os.path.join(frames_folder, selected_files[0]))
    w, h = first_frame.size

    for idx, file in enumerate(selected_files):
        with open(os.path.join(frames_folder, file), "rb") as f:
            optimized_data = optimize_image(f.read(), quality=quality, format=format)
            encoded = base64.b64encode(optimized_data).decode("utf-8")
            frames.append({
                "id": f"fr_{idx}",
                "w": w,
                "h": h,
                "u": "",
                "p": f"data:image/{format};base64," + encoded,
                "e": 1
            })
    
    return create_lottie_json(frames, w, h, 24)

def ask_user_preferences():
    # Выбор формата изображений
    while True:
        format_choice = input("Выберите формат изображений (1 - WebP, 2 - JPEG): ").strip()
        if format_choice in ['1', '2']:
            img_format = "webp" if format_choice == '1' else "jpeg"
            break
        print("Пожалуйста, введите 1 или 2")

    # Добавляем выбор режима качества
    while True:
        quality_mode = input("\nВыберите режим качества:\n1 - Максимальное качество (без сжатия)\n2 - Оптимизированное качество\nВаш выбор (1/2): ").strip()
        if quality_mode in ['1', '2']:
            optimize = quality_mode == '2'
            break
        print("Пожалуйста, введите 1 или 2")

    # Качество изображений (только для оптимизированного режима)
    quality = 100
    if optimize:
        while True:
            try:
                quality = int(input("Введите качество изображений (1-100): ").strip())
                if 1 <= quality <= 100:
                    break
                print("Значение должно быть от 1 до 100")
            except ValueError:
                print("Пожалуйста, введите число")

    # Добавляем выбор масштаба
    while True:
        try:
            scale = float(input("\nВведите масштаб кадров (1.0 - оригинальный размер, от 0.1 до 1.0 для уменьшения): ").strip())
            if 0.1 <= scale <= 1.0:
                break
            print("Значение должно быть от 0.1 до 1.0")
        except ValueError:
            print("Пожалуйста, введите число")

    # Количество кадров
    while True:
        try:
            target_frames = int(input("Сколько кадров должно быть в итоговой анимации? (рекомендуется 50-200): ").strip())
            if target_frames > 0:
                break
            print("Количество кадров должно быть положительным числом")
        except ValueError:
            print("Пожалуйста, введите число")

    # Выбор видео для конвертации
    src_folder = "src-video-to-convert"
    videos = [f for f in os.listdir(src_folder) if f.endswith(('.mp4', '.avi', '.mov'))]
    
    if not videos:
        sys.exit("Видео для конвертации не найдены в папке src-video-to-convert")

    selected_videos = []
    print("\nНайденные видео:")
    for i, video in enumerate(videos, 1):
        print(f"{i}. {video}")
    
    while True:
        choice = input("\nКонвертировать все видео? (y/n): ").strip().lower()
        if choice == 'y':
            selected_videos = videos
            break
        elif choice == 'n':
            while True:
                try:
                    idx = int(input(f"Введите номер видео (1-{len(videos)}): "))
                    if 1 <= idx <= len(videos):
                        selected_videos = [videos[idx-1]]
                        break
                    print(f"Пожалуйста, введите число от 1 до {len(videos)}")
                except ValueError:
                    print("Пожалуйста, введите число")
            break

    return {
        'format': img_format,
        'quality': quality,
        'optimize': optimize,
        'target_frames': target_frames,
        'selected_videos': selected_videos,
        'scale': scale
    }

def get_frames_folder(video_path):
    """Создает и возвращает путь к папке с кадрами для конкретного видео"""
    video_dir = os.path.dirname(video_path)
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    frames_folder = os.path.join(video_dir, f"{video_name}_frames")
    os.makedirs(frames_folder, exist_ok=True)
    return frames_folder

def main():
    # Создаем необходимые директории
    os.makedirs("src-video-to-convert", exist_ok=True)
    os.makedirs("output-lotties", exist_ok=True)

    # Получаем настройки от пользователя
    prefs = ask_user_preferences()
    
    for video in prefs['selected_videos']:
        print(f"\nОбработка видео: {video}")
        input_path = os.path.join("src-video-to-convert", video)
        output_name = os.path.splitext(video)[0] + ".json"
        output_path = os.path.join("output-lotties", output_name)
        
        # Получаем папку для кадров конкретного видео
        frames_folder = get_frames_folder(input_path)
        
        total_frames = get_total_frames(input_path)
        if total_frames is None:
            print(f"Ошибка при обработке {video}, пропускаем...")
            continue
        
        print("Общее количество кадров:", total_frames)
        step = max(1, total_frames // prefs['target_frames'])
        print("Будет извлекаться каждый", step, "кадр")
        
        # Извлекаем кадры с максимальным качеством
        extract_frames(input_path, frames_folder, step, quality=1, scale=prefs['scale'])
        print("Извлечение кадров завершено. Кодирование в Lottie JSON...")
        
        data = encode_frames_to_json(
            frames_folder, 
            prefs['target_frames'],
            quality=prefs['quality'],
            format=prefs['format']
        )
        json_data = json.dumps(data)
        
        with open(output_path, "w") as f:
            f.write(json_data)
        
        print(f"Lottie JSON сохранен в {output_path}")
        
        # Спрашиваем пользователя, нужно ли сохранить кадры
        keep_frames = input(f"\nСохранить извлеченные кадры в папке {frames_folder}? (y/n): ").strip().lower()
        if keep_frames != 'y':
            # Удаляем папку с кадрами
            for frame in os.listdir(frames_folder):
                os.remove(os.path.join(frames_folder, frame))
            os.rmdir(frames_folder)
            print("Папка с кадрами удалена")

    print("\nКонвертация завершена!")

if __name__ == "__main__":
    main()
