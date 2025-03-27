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

gif = False

# Global: ascii_chars pode ser alterado pela UI.
ascii_chars = " `.-:;+=xX$@"

# Para suportar drag & drop, use tkinterdnd2
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
except ImportError:
    print("Você precisa instalar o tkinterdnd2. Execute: pip install tkinterdnd2")
    exit()

# Função para travar o tamanho do console no Windows
def lock_console_size():
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
def ascii_video_cpu(video_path, new_width, custom_delay):
    os.system(f"mode con: cols={new_width} lines=40")
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
    time.sleep(custom_delay)
    
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
        time.sleep(custom_delay)
    cap.release()

# Conversão via GPU utilizando PyOpenCL com pré-carregamento e loading
def ascii_video_gpu(video_path, gpu_name, new_width, custom_delay, gif_mode=False):
    try:
        import pyopencl as cl
    except ImportError:
        print("PyOpenCL não está instalado. Usando conversão por CPU.")
        ascii_video_cpu(video_path, new_width, custom_delay)
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
        ascii_video_cpu(video_path, new_width, custom_delay)
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
    delay = 1 / fps if fps > 0 else custom_delay
    ret, frame = cap.read()
    if not ret:
        print("Vídeo vazio.")
        return
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    new_height = int((height / width) * new_width * 0.55)
    os.system(f"mode con: cols={new_width} lines={new_height}")
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
    
    # Aqui, em vez de pré-carregar os frames, processamos em tempo real com loop
    print("Iniciando reprodução (em loop: {})...".format(gif_mode))
    while True:
        ret, frame = cap.read()
        if not ret:
            if gif_mode:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            else:
                break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        out_frame = process_frame(gray)
        os.system('cls' if os.name=='nt' else 'clear')
        print(out_frame)
        time.sleep(custom_delay)
    cap.release()

# Interface gráfica com Tkinter (suporte a drag&drop e dropdown para seleção de dispositivo)
class App(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("2ASCII")
        self.geometry("400x300")

        # Imgs
        self.img_convert = tk.PhotoImage(file="assets/convert.png")
        self.img_about = tk.PhotoImage(file="assets/about.png")
        self.img_drop = tk.PhotoImage(file="assets/drop.png")
        
        btn_convert = tk.Button(self, image=self.img_convert, command=self.convert, bd=0, highlightthickness=0, relief="flat")
        btn_convert.place(x=45, y=20)
        
        btn_about = tk.Button(self, image=self.img_about, command=self.about, bd=0, highlightthickness=0, relief="flat")
        btn_about.place(x=45, y=50)
        
        self.drop_area = tk.Label(self, image=self.img_drop, bd=0, highlightthickness=0, relief="flat")
        self.drop_area.place(x=170, y=20)
        self.drop_area.drop_target_register(DND_FILES)
        self.drop_area.dnd_bind('<<Drop>>', self.drop)
        self.drop_area.bind("<Button-1>", self.browse_files)
        
        # Config
        self.ascii_label = tk.Label(self, text="ASCII Config:")
        self.ascii_label.place(x=50, y=100)

        self.width_slider = tk.Scale(self, from_=20, to=200, orient=tk.HORIZONTAL)
        self.width_slider.set(80)
        self.width_slider.place(x=35, y=120)
        
        
        self.ascii_entry = tk.Entry(self)
        self.ascii_entry.insert(0, " `.-:;+=xX$@")
        self.ascii_entry.place(x=25, y=180)

        self.delay_entry = tk.Entry(self)
        self.delay_entry.insert(0, "0.025")
        self.delay_entry.place(x=25, y=200)

        self.gif_mode_var = tk.BooleanVar(value=False)
        self.gif_checkbox = tk.Checkbutton(self, text="GIF Mode", variable=self.gif_mode_var)
        self.gif_checkbox.place(x=25, y=230)
        
        device_options = get_available_devices()
        self.selected_device = tk.StringVar()
        self.selected_device.set(device_options[0])
        dropdown = tk.OptionMenu(self, self.selected_device, *device_options)
        dropdown.place(x=20, y=260)
        
        self.file_path = None

    def convert(self):
        if self.file_path:
            global ascii_chars
            ascii_chars = self.ascii_entry.get()
            selected = self.selected_device.get()
            width_value = self.width_slider.get()
            delay_value = float(self.delay_entry.get())
            gif_mode_value = self.gif_mode_var.get()
            try:
                if os.name == 'nt':
                    subprocess.Popen(
                        [sys.executable, __file__, "--convert", self.file_path, "--device", selected, "--width", str(width_value), "--ascii_chars", ascii_chars, "--delay", str(delay_value), "--gif_mode", str(gif_mode_value)],
                        creationflags=subprocess.CREATE_NEW_CONSOLE)
                else:
                    subprocess.Popen(
                        [sys.executable, __file__, "--convert", self.file_path, "--device", selected, "--width", str(width_value), "--ascii_chars", ascii_chars, "--delay", str(delay_value), "--gif_mode", str(gif_mode_value)])
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

    def gif_mode(self):
        global gif
        gif = not gif

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
        custom_delay = 0.025
        if "--delay" in sys.argv:
            delay_index = sys.argv.index("--delay")
            custom_delay = float(sys.argv[delay_index + 1])
        if "--ascii_chars" in sys.argv:
            index = sys.argv.index("--ascii_chars")
            ascii_chars = sys.argv[index + 1]
        gif_mode = False
        if "--gif_mode" in sys.argv:
            gif_index = sys.argv.index("--gif_mode")
            gif_mode = sys.argv[gif_index + 1].lower() in ("true", "1", "yes")
        if device_name is None or device_name.lower().startswith("cpu"):
            ascii_video_cpu(video_file, new_width, custom_delay)
        else:
            if device_name.lower().startswith("gpu:"):
                device_name = device_name[4:].strip()
            ascii_video_gpu(video_file, device_name, new_width, custom_delay, gif_mode)
    else:
        app = App()
        app.mainloop()