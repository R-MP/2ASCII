import tkinter as tk
from tkinter import filedialog, messagebox
import os
import sys
import subprocess
import time
import cv2
import numpy as np
import ctypes
import threading
import tempfile

# Global: ascii_chars pode ser alterado pela UI.
ascii_chars = " .:-=+*+#%@"

# Global: se screen_lock for True, o bloqueio NÃO ocorrerá (permitindo redimensionar e tela cheia).
screen_lock = True

# Para suportar drag & drop, use tkinterdnd2
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
except ImportError:
    print("Você precisa instalar o tkinterdnd2. Execute: pip install tkinterdnd2")
    exit()

# Função para travar o tamanho do console no Windows
def lock_console_size():
    global screen_lock
    # Se screen_lock for True, ignora o bloqueio.
    if screen_lock:
        return
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        GWL_STYLE = -16
        WS_MAXIMIZEBOX = 0x00010000  # Impede maximizar
        WS_SIZEBOX = 0x00040000      # Impede redimensionar
        current_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
        new_style = current_style & ~WS_MAXIMIZEBOX & ~WS_SIZEBOX
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, new_style)

# Função que lista os dispositivos disponíveis (CPU e GPU)
def get_available_devices():
    try:
        import pyopencl as cl
        devices = []
        for platform in cl.get_platforms():
            for device in platform.get_devices():
                if device.type & cl.device_type.GPU:
                    devices.append(device.name.strip())
                elif device.type & cl.device_type.CPU:
                    devices.append(device.name.strip())
                else:
                    devices.append(device.name.strip())
        if not devices:
            return ["Nenhum dispositivo encontrado"]
        return devices
    except Exception as e:
        return ["PyOpenCL não instalado"]

# Função para extrair e tocar o áudio em 16-bit (PCM s16le)
def play_audio(video_path):
    temp_audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    temp_audio_name = temp_audio.name
    temp_audio.close()
    print(f"Extraindo áudio para: {temp_audio_name}")
    
    cmd_extract = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ar", "44100", "-ac", "1",
        "-c:a", "pcm_s16le", temp_audio_name
    ]
    result_extract = subprocess.run(cmd_extract, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print("ffmpeg output:", result_extract.stdout)
    print("ffmpeg error:", result_extract.stderr)
    
    if not os.path.exists(temp_audio_name):
        print("Erro: o arquivo de áudio não foi criado.")
        return
    
    cmd_play = ["ffplay", "-nodisp", "-autoexit", temp_audio_name]
    try:
        subprocess.Popen(cmd_play, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        print("Erro ao iniciar ffplay:", e)

# Conversão via CPU (método tradicional) – usa a variável global ascii_chars
def ascii_video_cpu(video_path, new_width):
    os.system(f"mode con: cols={new_width} lines=40")
    if not screen_lock:
        lock_console_size()
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Não foi possível abrir o vídeo.")
        return
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    ret, frame = cap.read()
    if not ret:
        print("Vídeo vazio.")
        return
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    new_height = int((height / width) * new_width * 0.55)
    os.system(f"mode con: cols={new_width} lines={new_height}")
    
    global ascii_chars
    out_frame = ""
    gray = cv2.resize(gray, (new_width, new_height))
    for row in gray:
        for pixel in row:
            index = int(pixel / 256 * len(ascii_chars))
            if index >= len(ascii_chars):
                index = len(ascii_chars) - 1
            out_frame += ascii_chars[index]
        out_frame += "\n"
    os.system('cls' if os.name=='nt' else 'clear')
    print(out_frame)
    time.sleep(0.025)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (new_width, new_height))
        out_frame = ""
        for row in gray:
            for pixel in row:
                index = int(pixel / 256 * len(ascii_chars))
                if index >= len(ascii_chars):
                    index = len(ascii_chars) - 1
                out_frame += ascii_chars[index]
            out_frame += "\n"
        os.system('cls' if os.name=='nt' else 'clear')
        print(out_frame)
        time.sleep(0.025)
    cap.release()

# Conversão via GPU utilizando PyOpenCL com pré-carregamento e loading
def ascii_video_gpu(video_path, gpu_name, new_width):
    try:
        import pyopencl as cl
    except ImportError:
        print("PyOpenCL não está instalado. Usando conversão por CPU.")
        ascii_video_cpu(video_path, new_width)
        return
    
    global ascii_chars
    num_chars = len(ascii_chars)
    
    platforms = cl.get_platforms()
    chosen_device = None
    for platform in platforms:
        for device in platform.get_devices():
            if (device.type & cl.device_type.GPU) and (gpu_name in device.name):
                chosen_device = device
                break
        if chosen_device:
            break
    if not chosen_device:
        print("GPU selecionada não encontrada. Usando conversão por CPU.")
        ascii_video_cpu(video_path, new_width)
        return
    
    ctx = cl.Context([chosen_device])
    queue = cl.CommandQueue(ctx)
    kernel_code = """
    __kernel void convert_to_ascii(__global const uchar *input, __global uchar *output, const int num_chars) {
        int i = get_global_id(0);
        output[i] = (uchar)((input[i] * num_chars) / 256);
    }
    """
    program = cl.Program(ctx, kernel_code).build()
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Não foi possível abrir o vídeo.")
        return
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    delay = 1 / fps if fps > 0 else 0.033
    ret, frame = cap.read()
    if not ret:
        print("Vídeo vazio.")
        return
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    new_height = int((height / width) * new_width * 0.55)
    os.system(f"mode con: cols={new_width} lines={new_height}")
    if not screen_lock:
        lock_console_size()
    
    def process_frame(gray_frame):
        resized = cv2.resize(gray_frame, (new_width, new_height))
        flat_gray = resized.flatten().astype(np.uint8)
        mf = cl.mem_flags
        input_buf = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=flat_gray)
        output_buf = cl.Buffer(ctx, mf.WRITE_ONLY, flat_gray.nbytes)
        global_size = (flat_gray.size,)
        program.convert_to_ascii(queue, global_size, None, input_buf, output_buf, np.int32(num_chars))
        result = np.empty_like(flat_gray)
        cl.enqueue_copy(queue, result, output_buf)
        result = result.reshape((new_height, new_width))
        out_frame = ""
        for row in result:
            out_frame += "".join(ascii_chars[pix] for pix in row) + "\n"
        return out_frame
    
    ascii_frames = []
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    current_frame = 1
    ascii_frames.append(process_frame(gray))
    print(f"Carregando frames: {current_frame}/{total_frames}", end="\r")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        current_frame += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        ascii_frames.append(process_frame(gray))
        print(f"Carregando frames: {current_frame}/{total_frames}", end="\r")
    cap.release()
    print("\nCarregamento concluído. Iniciando reprodução...")
    
    play_audio(video_path)
    
    for frame in ascii_frames:
        os.system('cls' if os.name=='nt' else 'clear')
        print(frame)
        time.sleep(delay)

# Interface gráfica com Tkinter (suporte a drag&drop e dropdown para seleção de dispositivo)
class App(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("2ASCII")
        self.geometry("400x300")
        
        btn_convert = tk.Button(self, text="convert", command=self.convert)
        btn_convert.place(x=65, y=50)
        
        btn_about = tk.Button(self, text="about", command=self.about)
        btn_about.place(x=70, y=100)
        
        self.drop_area = tk.Label(self, text="Arraste ou clique para anexar mídia", relief="groove", width=30, height=15)
        self.drop_area.place(x=170, y=20)
        self.drop_area.drop_target_register(DND_FILES)
        self.drop_area.dnd_bind('<<Drop>>', self.drop)
        self.drop_area.bind("<Button-1>", self.browse_files)
        
        self.width_slider = tk.Scale(self, from_=20, to=200, orient=tk.HORIZONTAL, label="ASCII Width")
        self.width_slider.set(80)
        self.width_slider.place(x=45, y=150)
        
        self.ascii_label = tk.Label(self, text="ASCII Chars:")
        self.ascii_label.place(x=45, y=190)
        self.ascii_entry = tk.Entry(self)
        self.ascii_entry.insert(0, " .:-=+*+#%@")
        self.ascii_entry.place(x=45, y=210)
        
        self.lock_checkbox = tk.Checkbutton(self, text="Disable Console Lock", command=self.toggle_lock)
        self.lock_checkbox.place(x=20, y=230)
        
        device_options = get_available_devices()
        self.selected_device = tk.StringVar()
        self.selected_device.set(device_options[0])
        dropdown = tk.OptionMenu(self, self.selected_device, *device_options)
        dropdown.place(x=20, y=260)
        
        self.file_path = None

    def toggle_lock(self):
        global screen_lock
        screen_lock = not screen_lock
        print("screen_lock:", screen_lock)

    def convert(self):
        if self.file_path:
            global ascii_chars
            ascii_chars = self.ascii_entry.get()
            selected = self.selected_device.get()
            width_value = self.width_slider.get()
            try:
                if os.name == 'nt':
                    subprocess.Popen(
                        [sys.executable, __file__, "--convert", self.file_path, "--device", selected, "--width", str(width_value), "--ascii_chars", ascii_chars],
                        creationflags=subprocess.CREATE_NEW_CONSOLE)
                else:
                    subprocess.Popen(
                        [sys.executable, __file__, "--convert", self.file_path, "--device", selected, "--width", str(width_value), "--ascii_chars", ascii_chars])
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível iniciar a conversão:\n{str(e)}")
        else:
            messagebox.showwarning("Aviso", "Nenhuma mídia anexada.")

    def about(self):
        messagebox.showinfo("About", "Este programa converte vídeos para ASCII e os reproduz em um prompt de comando.\n\nCustomize conforme necessário.")
    
    def drop(self, event):
        files = self.tk.splitlist(event.data)
        if files:
            self.file_path = files[0]
            self.drop_area.config(text=f"Mídia anexada:\n{self.file_path}")
    
    def browse_files(self, event):
        file_path = filedialog.askopenfilename()
        if file_path:
            self.file_path = file_path
            self.drop_area.config(text=f"Mídia anexada:\n{self.file_path}")

if __name__ == "__main__":
    if "--convert" in sys.argv:
        try:
            convert_index = sys.argv.index("--convert")
            video_file = sys.argv[convert_index + 1]
        except:
            print("Caminho do vídeo não fornecido.")
            sys.exit(1)
        device_name = None
        if "--device" in sys.argv:
            device_index = sys.argv.index("--device")
            device_name = sys.argv[device_index + 1]
        new_width = 160
        if "--width" in sys.argv:
            width_index = sys.argv.index("--width")
            new_width = int(sys.argv[width_index + 1])
        if "--ascii_chars" in sys.argv:
            index = sys.argv.index("--ascii_chars")
            ascii_chars = sys.argv[index + 1]
        if device_name is None or device_name.lower().startswith("cpu"):
            ascii_video_cpu(video_file, new_width)
        else:
            if device_name.lower().startswith("gpu:"):
                device_name = device_name[4:].strip()
            ascii_video_gpu(video_file, device_name, new_width)
    else:
        app = App()
        app.mainloop()
