import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import queue
from pathlib import Path
import bundler_logic # Import the core logic

class CodeBundlerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Code2Text GUI Bundler")
        # self.root.geometry("700x550") # Optional: set initial size

        # Variables
        self.main_file_path = tk.StringVar()
        self.output_file_path = tk.StringVar()
        self.project_root_path = tk.StringVar()
        self.is_processing = False
        self.message_queue = queue.Queue()

        # Configure root padding
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1) # Make log area expandable

        # --- GUI Elements ---
        # Input File Section
        input_frame = ttk.LabelFrame(root, text="Input Project File", padding=(10, 5))
        input_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        input_frame.columnconfigure(1, weight=1)

        ttk.Label(input_frame, text="Main Python File:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.main_file_entry = ttk.Entry(input_frame, textvariable=self.main_file_path, state='readonly', width=60)
        self.main_file_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.browse_main_btn = ttk.Button(input_frame, text="Browse...", command=self.select_main_file)
        self.browse_main_btn.grid(row=0, column=2, padx=5, pady=5)

        # Output File Section
        output_frame = ttk.LabelFrame(root, text="Output Bundled File", padding=(10, 5))
        output_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        output_frame.columnconfigure(1, weight=1)

        ttk.Label(output_frame, text="Output Text File:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.output_file_entry = ttk.Entry(output_frame, textvariable=self.output_file_path, state='readonly', width=60)
        self.output_file_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.browse_output_btn = ttk.Button(output_frame, text="Save As...", command=self.select_output_file)
        self.browse_output_btn.grid(row=0, column=2, padx=5, pady=5)

        # Project Root Display
        root_frame = ttk.LabelFrame(root, text="Detected Project Info", padding=(10, 5))
        root_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        root_frame.columnconfigure(1, weight=1)

        ttk.Label(root_frame, text="Detected Root:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.project_root_entry = ttk.Entry(root_frame, textvariable=self.project_root_path, state='readonly', width=60)
        self.project_root_entry.grid(row=0, column=1, padx=(5, 15), pady=5, sticky="ew") # Added more padding

        # Log Area
        log_frame = ttk.LabelFrame(root, text="Status & Output Log", padding=(10, 5))
        log_frame.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_area = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=15, state='disabled')
        self.log_area.grid(row=0, column=0, sticky="nsew")
        # Add tags for styling later if needed (e.g., errors)
        self.log_area.tag_config("ERROR", foreground="red")
        self.log_area.tag_config("WARNING", foreground="orange")
        self.log_area.tag_config("INFO", foreground="blue")
        self.log_area.tag_config("SUCCESS", foreground="green")


        # Action Button
        action_frame = ttk.Frame(root, padding=(10, 10))
        action_frame.grid(row=4, column=0, sticky="e") # Align button right

        self.generate_btn = ttk.Button(action_frame, text="Generate Bundled File", command=self.start_generation, state='disabled')
        self.generate_btn.pack()

        # Start polling the queue
        self.root.after(100, self.check_queue)


    def log_message(self, message: str, level: str = "NORMAL"):
        """Appends a message to the log area, handling state and scrolling."""
        self.log_area.configure(state='normal')
        tag = None
        if message.lower().startswith("error:") or level == "ERROR":
             tag = "ERROR"
        elif message.lower().startswith("warning:") or level == "WARNING":
             tag = "WARNING"
        elif message.lower().startswith("detected project root:") or \
             message.lower().startswith("topological sort complete") or \
             message.lower().startswith("bundling process finished") or \
             level == "INFO":
             tag = "INFO"
        elif level == "SUCCESS":
             tag = "SUCCESS"

        if tag:
            self.log_area.insert(tk.END, message + '\n', tag)
        else:
            self.log_area.insert(tk.END, message + '\n')

        self.log_area.see(tk.END) # Scroll to the end
        self.log_area.configure(state='disabled')
        # self.root.update_idletasks() # Force GUI update, use carefully


    def select_main_file(self):
        """Opens a dialog to select the main Python file."""
        filetypes = (("Python files", "*.py"), ("All files", "*.*"))
        filepath = filedialog.askopenfilename(title="Select Main Python File", filetypes=filetypes)
        if filepath:
            self.main_file_path.set(filepath)
            self.project_root_path.set("Detecting...") # Indicate detection
            # Try to detect project root immediately
            try:
                root = bundler_logic.find_project_root(Path(filepath))
                if root:
                    self.project_root_path.set(str(root))
                else:
                    # Use parent dir as fallback if find_project_root returns None but we need *something*
                    self.project_root_path.set(str(Path(filepath).parent) + " (Fallback - No marker found)")
            except Exception as e:
                self.project_root_path.set(f"Error detecting root: {e}")
            self.check_button_state()

    def select_output_file(self):
        """Opens a dialog to select the output text file location."""
        filetypes = (("Text files", "*.txt"), ("All files", "*.*"))
        filepath = filedialog.asksaveasfilename(title="Save Bundled File As", filetypes=filetypes, defaultextension=".txt")
        if filepath:
            self.output_file_path.set(filepath)
            self.check_button_state()

    def check_button_state(self):
        """Enables or disables the Generate button based on input/output paths."""
        if self.main_file_path.get() and self.output_file_path.get() and not self.is_processing:
            self.generate_btn.config(state='normal')
        else:
            self.generate_btn.config(state='disabled')

    def start_generation(self):
        """Starts the bundling process in a separate thread."""
        if self.is_processing:
            return

        main_file = self.main_file_path.get()
        output_file = self.output_file_path.get()

        if not main_file or not output_file:
            messagebox.showerror("Error", "Please select both main input file and output file locations.")
            return

        self.is_processing = True
        self.check_button_state() # Disable button
        self.log_area.configure(state='normal')
        self.log_area.delete(1.0, tk.END) # Clear previous log
        self.log_area.configure(state='disabled')

        # Function to run in the thread
        def thread_target():
            try:
                # Pass a lambda that puts messages into the queue
                success = bundler_logic.run_bundling_process(
                    main_file,
                    output_file,
                    lambda msg: self.message_queue.put(("LOG", msg))
                )
                if success:
                    self.message_queue.put(("DONE", "SUCCESS"))
                else:
                    self.message_queue.put(("DONE", "FAILURE"))
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                self.message_queue.put(("LOG", f"Critical Error in thread: {e}\n{error_details}", "ERROR"))
                self.message_queue.put(("DONE", "CRITICAL_ERROR"))

        # Create and start the thread
        self.processing_thread = threading.Thread(target=thread_target, daemon=True)
        self.processing_thread.start()

    def check_queue(self):
        """Checks the message queue for updates from the worker thread."""
        try:
            while True: # Process all messages currently in queue
                message_type, payload = self.message_queue.get_nowait()

                if message_type == "LOG":
                    level = "NORMAL"
                    if isinstance(payload, tuple) and len(payload) == 2:
                        message, level = payload
                    else:
                         message = payload
                    self.log_message(message, level)
                elif message_type == "DONE":
                    self.is_processing = False
                    self.check_button_state() # Re-enable button
                    if payload == "SUCCESS":
                        self.log_message("Process completed successfully!", "SUCCESS")
                        # Optional: show success message box
                        # messagebox.showinfo("Success", f"Bundled file created:\n{self.output_file_path.get()}")
                    elif payload == "FAILURE":
                         self.log_message("Process finished with errors.", "ERROR")
                         messagebox.showerror("Error", "Bundling process failed. Check the log for details.")
                    elif payload == "CRITICAL_ERROR":
                         self.log_message("Process terminated due to a critical error.", "ERROR")
                         messagebox.showerror("Critical Error", "An unexpected error occurred. Check the log for details.")

        except queue.Empty:
            pass # No messages currently

        # Reschedule the check
        self.root.after(100, self.check_queue)


if __name__ == "__main__":
    root = tk.Tk()
    app = CodeBundlerApp(root)
    root.mainloop()