"""Read-only PDF review of a draft before committing it to history."""
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import ImageTk
import pypdfium2 as pdfium


class PrescriptionPreview(tk.Toplevel):
    def __init__(self, parent, pdf_bytes, on_save, *, title="Review prescription - not saved yet", hint="Review the patient, medicines, date and signature.", save_label="Save prescription"):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.geometry("850x760"); self.minsize(650, 480)
        self.transient(parent)
        self._document = pdfium.PdfDocument(pdf_bytes)
        self._page = 0
        self._job = None
        self._on_save = on_save
        self.zoom = tk.StringVar(value="Fit")
        self.page_label = tk.StringVar()
        self.columnconfigure(0, weight=1); self.rowconfigure(1, weight=1)
        top = ttk.Frame(self, padding=10); top.grid(row=0,column=0,columnspan=2,sticky="ew")
        ttk.Label(top,text=hint).pack(side="left")
        ttk.Combobox(top,textvariable=self.zoom,values=["Fit","100%","150%","200%"],state="readonly",width=7).pack(side="right")
        self.canvas = tk.Canvas(self,bg="#dce3eb",highlightthickness=0,yscrollincrement=20,xscrollincrement=20)
        self.canvas.grid(row=1,column=0,sticky="nsew")
        vertical=ttk.Scrollbar(self,orient="vertical",command=self.canvas.yview);vertical.grid(row=1,column=1,sticky="ns")
        horizontal=ttk.Scrollbar(self,orient="horizontal",command=self.canvas.xview);horizontal.grid(row=2,column=0,sticky="ew")
        self.canvas.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        self.canvas.bind("<MouseWheel>",self._wheel)
        self.canvas.bind("<Shift-MouseWheel>",lambda e:self._wheel(e,horizontal=True))
        self.canvas.bind("<Configure>",self._schedule)
        self.zoom.trace_add("write",self._schedule)
        bottom=ttk.Frame(self,padding=10);bottom.grid(row=3,column=0,columnspan=2,sticky="ew")
        self.previous=ttk.Button(bottom,text="Previous",command=lambda:self._turn(-1));self.previous.pack(side="left")
        ttk.Label(bottom,textvariable=self.page_label).pack(side="left",padx=10)
        self.next=ttk.Button(bottom,text="Next",command=lambda:self._turn(1));self.next.pack(side="left")
        self.save_button=ttk.Button(bottom,text=save_label,style="Accent.TButton",command=self._save);self.save_button.pack(side="right")
        ttk.Button(bottom,text="Back to editing",command=self.destroy).pack(side="right",padx=8)
        self.bind("<Escape>",lambda e:self.destroy())
        self.bind("<Destroy>",self._closed)
        self.deiconify();self.grab_set();self._schedule()

    def _wheel(self,event,horizontal=False):
        move=self.canvas.xview_scroll if horizontal else self.canvas.yview_scroll
        move(-int(event.delta/120)*3,"units")
        return "break"

    def _schedule(self,*_):
        if self._job:self.after_cancel(self._job)
        self._job=self.after(50,self._render)

    def _render(self):
        self._job=None
        page=self._document[self._page]
        try:
            width,height=page.get_size()
            scale=min(max(50,self.canvas.winfo_width()-32)/width,max(50,self.canvas.winfo_height()-32)/height) if self.zoom.get()=="Fit" else float(self.zoom.get().rstrip("%"))/100*96/72
            bitmap=page.render(scale=scale)
            try:image=bitmap.to_pil().copy()
            finally:bitmap.close()
        finally:page.close()
        self._photo=ImageTk.PhotoImage(image)
        x=max(16,(self.canvas.winfo_width()-image.width)/2);y=max(16,(self.canvas.winfo_height()-image.height)/2)
        self.canvas.delete("all");self.canvas.create_image(x,y,image=self._photo,anchor="nw")
        self.canvas.configure(scrollregion=(0,0,max(self.canvas.winfo_width(),image.width+32),max(self.canvas.winfo_height(),image.height+32)))
        self.page_label.set(f"Page {self._page+1} of {len(self._document)}")
        self.previous.state(["disabled"] if self._page==0 else ["!disabled"])
        self.next.state(["disabled"] if self._page==len(self._document)-1 else ["!disabled"])

    def _turn(self,step):
        self._page=max(0,min(len(self._document)-1,self._page+step))
        self.canvas.yview_moveto(0);self.canvas.xview_moveto(0);self._render()

    def _save(self):
        self.save_button.state(["disabled"])
        try:
            if self._on_save():self.destroy()
            else:self.save_button.state(["!disabled"])
        except Exception as exc:
            self.save_button.state(["!disabled"])
            messagebox.showerror("Could not save",str(exc),parent=self)

    def _closed(self,event):
        if event.widget is self:
            if self._job:self.after_cancel(self._job)
            self._document.close()
