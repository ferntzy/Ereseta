"""Visual prescription editor backed by the production PDF renderer."""
from __future__ import annotations
import copy
import json
import os
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from PIL import ImageTk
import pypdfium2 as pdfium
from . import config, theme
from .layout_controls import PAPER_PRESETS, preview_toolbar, zoom_step, settings_notebook
from .database import get_all_physicians, get_setting, set_setting
from .pdf_generator import template_pdf_bytes, generate_template_preview, open_file


class TemplateEditor(tk.Frame):
    PAGE_PRESETS = PAPER_PRESETS
    MARGIN_PRESETS = {"Small": .25, "Normal": .40, "Wide": .60}
    IMAGE_NAMES = {"Doctor e-signature": "sig", "Hospital logo": "logo", "Rx symbol": "rx"}

    def __init__(self, parent, app=None):
        super().__init__(parent, bg=theme.COLOR_BG)
        self.app = app
        self._preview_job = None
        self._pdf_cache_key = None
        self._pdf_bytes = None
        self._image_boxes = {}
        self._drag = None
        self.dirty=False
        self._focus_signature=False
        self.template = self._load_template()
        self.status_var = tk.StringVar(value="Drag pictures on the PDF. Click Save layout when ready.")
        self.selected_image = tk.StringVar(value="Doctor e-signature")
        self.preview_doctor = tk.StringVar(value="Current record doctor")
        self.signature_hint = tk.StringVar()
        self.zoom_var = tk.StringVar(value="Fit")
        self.guides_var = tk.BooleanVar(value=True)
        self.page_preset_var = tk.StringVar()
        self.margin_preset_var = tk.StringVar()
        self.header_font_var = tk.IntVar()
        self.body_font_var = tk.IntVar()
        self.accent_var = tk.StringVar()
        self.show_motto_var = tk.BooleanVar()
        self.transparent_images_var = tk.BooleanVar()
        for key in self.IMAGE_NAMES.values():
            setattr(self, f"{key}_enabled_var", tk.BooleanVar())
            setattr(self, f"{key}_path_var", tk.StringVar())
            for part in ("x", "y", "w", "h"):
                setattr(self, f"{key}_{part}_var", tk.DoubleVar())
        self._load_variables(self.template)
        watched = [self.page_preset_var, self.margin_preset_var, self.header_font_var,
                   self.body_font_var, self.accent_var, self.show_motto_var, self.transparent_images_var]
        for key in self.IMAGE_NAMES.values():
            watched.extend(self._image_vars(key))
            watched.extend([getattr(self,f"{key}_enabled_var"),getattr(self,f"{key}_path_var")])
        for variable in watched:
            variable.trace_add("write", self._on_setting_changed)
        for variable in (self.zoom_var,self.guides_var,self.selected_image,self.preview_doctor):
            variable.trace_add("write",lambda *_:self._schedule_preview())
        self.columnconfigure(0,weight=1);self.rowconfigure(1,weight=1)
        self._build_ui()
        self.bind("<Map>",lambda event:self._refresh_editor() if event.widget is self else None)
        self.bind("<Destroy>",self._destroyed)
        self._schedule_preview()

    def _load_template(self):
        template=copy.deepcopy(config.DEFAULT_TEMPLATE)
        saved=get_setting("template",{}) or {}
        template.update(saved)
        for key in ("logo","signature_img"):
            template[key]={**config.DEFAULT_TEMPLATE.get(key,{}),**saved.get(key,{})}
        template["rx_symbol"]={"enabled":template.get("show_rx_symbol",True),"path":template.get("rx_symbol_path",""),
            "x_pct":.07,"y_pct":.30,"w_pct":.10,"h_pct":.08,**template.get("rx_symbol",{})}
        return template

    def _load_variables(self,t):
        self.PAGE_PRESETS=dict(type(self).PAGE_PRESETS)
        dimensions=(t.get("page_width_in",5.5),t.get("page_height_in",8.5))
        page=next((name for name,size in self.PAGE_PRESETS.items() if size==dimensions),None)
        if page is None:
            page="Saved paper size";self.PAGE_PRESETS[page]=dimensions
        self.page_preset_var.set(page)
        self.MARGIN_PRESETS=dict(type(self).MARGIN_PRESETS)
        margin=t.get("margin_in",.4)
        margin_name=next((name for name,size in self.MARGIN_PRESETS.items() if abs(size-margin)<.001),None)
        if margin_name is None:
            margin_name="Saved edge spacing";self.MARGIN_PRESETS[margin_name]=margin
        self.margin_preset_var.set(margin_name)
        self.header_font_var.set(t.get("header_font_size",11));self.body_font_var.set(t.get("body_font_size",9))
        self.accent_var.set(t.get("accent_color","#0f172a"));self.show_motto_var.set(t.get("show_motto",True))
        self.transparent_images_var.set(t.get("transparent_images",True))
        for key,cfg_key,defaults in [("sig","signature_img",(.58,.16,.28,.07)),("logo","logo",(.42,.04,.16,.09)),("rx","rx_symbol",(.07,.30,.10,.08))]:
            cfg=t.get(cfg_key,{})
            values=[float(cfg.get(f"{part}_pct",default)) for part,default in zip(("x","y","w","h"),defaults)]
            if key=="sig":values[1]=1-values[1]-values[3]
            values[2]=max(.02,min(.9,values[2]));values[3]=max(.02,min(.9,values[3]))
            values[0]=max(0,min(1-values[2],values[0]));values[1]=max(0,min(1-values[3],values[1]))
            for variable,value in zip(self._image_vars(key),values):variable.set(value)
            getattr(self,f"{key}_enabled_var").set(cfg.get("show_assigned",True) if key=="sig" else cfg.get("enabled",True))
            getattr(self,f"{key}_path_var").set(cfg.get("path",""))

    def _image_vars(self,key):
        return [getattr(self,f"{key}_{part}_var") for part in ("x","y","w","h")]

    def _on_setting_changed(self,*_):
        self.dirty=True
        self.status_var.set("Unsaved layout changes. Click Save layout to keep them.")
        self._schedule_preview()

    def _schedule_preview(self):
        if self._preview_job:self.after_cancel(self._preview_job)
        self._preview_job=self.after(60,self._refresh_preview)

    def _destroyed(self,event):
        if event.widget is self and self._preview_job:
            self.after_cancel(self._preview_job);self._preview_job=None

    def _build_ui(self):
        header=ttk.Frame(self,style="Card.TFrame",padding=14);header.grid(row=0,column=0,sticky="ew")
        ttk.Label(header,text="Prescription layout",font=("Segoe UI",16,"bold")).pack(anchor="w")
        ttk.Label(header,text="This is the actual PDF layout with sample patient details. Drag pictures, zoom in, then Save layout.",style="Hint.TLabel").pack(anchor="w",pady=(5,0))
        main=ttk.Frame(self,style="Card.TFrame");main.grid(row=1,column=0,sticky="nsew",pady=8)
        main.columnconfigure(1,weight=1);main.rowconfigure(0,weight=1)
        side=ttk.Frame(main);side.grid(row=0,column=0,sticky="ns")
        side.rowconfigure(0,weight=1);side.columnconfigure(0,weight=1)
        self.settings_canvas=tk.Canvas(side,width=310,height=450,bg="white",highlightthickness=0,yscrollincrement=16)
        self.settings_canvas.grid(row=0,column=0,sticky="nsew")
        sb=ttk.Scrollbar(side,orient="vertical",command=self.settings_canvas.yview);sb.grid(row=0,column=1,sticky="ns")
        self.settings_canvas.configure(yscrollcommand=sb.set)
        self.settings_panel=ttk.Frame(self.settings_canvas,style="Card.TFrame",padding=14)
        self.settings_window=self.settings_canvas.create_window((0,0),window=self.settings_panel,anchor="nw")
        self.settings_panel.bind("<Configure>",lambda e:self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox("all")))
        self.settings_canvas.bind("<Configure>",lambda e:self.settings_canvas.itemconfigure(self.settings_window,width=e.width))
        self._build_controls();self._build_preview_area(main)
        actions=ttk.Frame(self,style="Card.TFrame",padding=10);actions.grid(row=2,column=0,sticky="ew")
        ttk.Label(actions,textvariable=self.status_var,style="Hint.TLabel",wraplength=280).pack(side="left")
        ttk.Button(actions,text="Save layout",style="Accent.TButton",command=self._save_template).pack(side="right")
        ttk.Button(actions,text="Print preview",command=self._preview_pdf).pack(side="right",padx=6)
        ttk.Button(actions,text="Restore defaults",command=self._reset_defaults).pack(side="right")

    def _section(self,title,hint):
        frame=ttk.Frame(getattr(self,"_controls_parent",self.settings_panel),style="Card.TFrame");frame.pack(fill="x",pady=(0,16))
        ttk.Label(frame,text=title,font=("Segoe UI",10,"bold")).pack(anchor="w")
        ttk.Label(frame,text=hint,style="Hint.TLabel",wraplength=270).pack(anchor="w",pady=(4,8))
        return frame

    def _build_controls(self):
        groups=settings_notebook(self.settings_panel);groups.pack(fill="both",expand=True)
        paper=ttk.Frame(groups,style="Card.TFrame",padding=6);pictures=ttk.Frame(groups,style="Card.TFrame",padding=6)
        groups.add(paper,text="Paper & text");groups.add(pictures,text="Pictures & signature")
        self._controls_parent=pictures
        section=self._section("Pictures & signature","Select an item, then drag its outline on the paper.")
        ttk.Combobox(section,textvariable=self.selected_image,values=list(self.IMAGE_NAMES),state="readonly").pack(fill="x")
        row=ttk.Frame(section);row.pack(fill="x",pady=8)
        for title,factor in [("Smaller",.9),("Bigger",1.1)]:
            ttk.Button(row,text=title,command=lambda f=factor:self._resize_image(f)).pack(side="left",expand=True,fill="x")
        row=ttk.Frame(section);row.pack(fill="x",pady=(0,8))
        for title,dx,dy in [("Left",-.01,0),("Up",0,-.01),("Down",0,.01),("Right",.01,0)]:
            ttk.Button(row,text=title,width=5,command=lambda x=dx,y=dy:self._move_image(x,y)).pack(side="left",expand=True,fill="x")
        ttk.Button(section,text="Put signature above doctor's name",command=self._place_signature).pack(fill="x",pady=(0,8))
        ttk.Label(section,text="Preview signature from").pack(anchor="w")
        self.doctor_picker=ttk.Combobox(section,textvariable=self.preview_doctor,state="readonly",postcommand=self._refresh_doctors)
        self.doctor_picker.pack(fill="x",pady=4);self._refresh_doctors()
        ttk.Label(section,textvariable=self.signature_hint,style="Hint.TLabel",wraplength=270).pack(anchor="w",pady=4)
        ttk.Checkbutton(section,text="Print assigned doctor's signature",variable=self.sig_enabled_var).pack(anchor="w",pady=4)
        ttk.Checkbutton(section,text="Remove white picture backgrounds",variable=self.transparent_images_var).pack(anchor="w",pady=4)
        ttk.Label(section,text="Position applies to all doctors. Assign images in New Prescription.",style="Hint.TLabel",wraplength=270).pack(anchor="w",pady=4)
        for key,title in [("logo","Hospital logo"),("rx","Rx symbol")]:
            row=ttk.Frame(section,style="Card.TFrame");row.pack(fill="x",pady=4)
            ttk.Checkbutton(row,text=title,variable=getattr(self,f"{key}_enabled_var")).pack(side="left")
            ttk.Button(row,text="Choose image",command=lambda k=key:self._pick_image(k)).pack(side="right")
        self._controls_parent=paper
        section=self._section("Paper","Choose the paper you use in your printer.")
        ttk.Label(section,text="Paper size").pack(anchor="w")
        self.paper_picker=ttk.Combobox(section,textvariable=self.page_preset_var,values=list(self.PAGE_PRESETS),state="readonly");self.paper_picker.pack(fill="x",pady=5)
        ttk.Label(section,text="Blank space around the edges").pack(anchor="w")
        self.margin_picker=ttk.Combobox(section,textvariable=self.margin_preset_var,values=list(self.MARGIN_PRESETS),state="readonly");self.margin_picker.pack(fill="x",pady=5)
        section=self._section("Text","Choose readable text sizes and a color.")
        for title,var,lo,hi in [("Hospital name size",self.header_font_var,6,30),("Medicine text size",self.body_font_var,6,22)]:
            row=ttk.Frame(section,style="Card.TFrame");row.pack(fill="x",pady=4)
            ttk.Label(row,text=title).pack(side="left");ttk.Spinbox(row,textvariable=var,from_=lo,to=hi,width=5).pack(side="right")
        ttk.Checkbutton(section,text="Show hospital motto",variable=self.show_motto_var).pack(anchor="w",pady=6)
        ttk.Button(section,text="Choose text color",command=self._pick_color).pack(fill="x")

    def _build_preview_area(self,parent):
        panel=ttk.Frame(parent,style="Card.TFrame",padding=10);panel.grid(row=0,column=1,sticky="nsew")
        panel.columnconfigure(0,weight=1);panel.rowconfigure(2,weight=1)
        bar=preview_toolbar(panel,self.zoom_var,self._zoom,self.zoom_signature)
        bar.grid(row=0,column=0,columnspan=2,sticky="ew",pady=(0,6))
        ttk.Checkbutton(panel,text="Show drag outlines (not printed)",variable=self.guides_var).grid(row=1,column=0,sticky="w",pady=(0,6))
        self.preview_canvas=tk.Canvas(panel,bg="#DDE1E6",highlightthickness=0,width=300,height=420,yscrollincrement=20,xscrollincrement=20)
        self.preview_canvas.grid(row=2,column=0,sticky="nsew")
        vs=ttk.Scrollbar(panel,orient="vertical",command=self.preview_canvas.yview);vs.grid(row=2,column=1,sticky="ns")
        hs=ttk.Scrollbar(panel,orient="horizontal",command=self.preview_canvas.xview);hs.grid(row=3,column=0,sticky="ew")
        self.preview_canvas.configure(yscrollcommand=vs.set,xscrollcommand=hs.set,cursor="hand2")
        self.preview_canvas.bind("<Configure>",lambda e:self._schedule_preview())
        self.preview_canvas.bind("<Control-MouseWheel>",lambda e:self._zoom(1 if e.delta>0 else -1))
        self.preview_canvas.bind("<Shift-MouseWheel>",self._horizontal_scroll)
        self.preview_canvas.bind("<ButtonPress-1>",self._start_drag)
        self.preview_canvas.bind("<B1-Motion>",self._drag_image)
        self.preview_canvas.bind("<ButtonRelease-1>",self._end_drag)

    def _refresh_doctors(self):
        self._doctors={row["name"]:dict(row) for row in get_all_physicians()}
        self.doctor_picker["values"]=["Current record doctor",*self._doctors]

    def _signature_path(self):
        if self.preview_doctor.get()=="Current record doctor":
            return self.app.ph_signature.get() if self.app and hasattr(self.app,"ph_signature") else ""
        return self._doctors.get(self.preview_doctor.get(),{}).get("signature_path") or ""

    def _refresh_editor(self):
        self._refresh_doctors();self._refresh_preview()

    def _refresh_preview(self):
        if self._preview_job:self.after_cancel(self._preview_job)
        self._preview_job=None
        if not hasattr(self,"preview_canvas"):return
        canvas=self.preview_canvas;cw,ch=canvas.winfo_width(),canvas.winfo_height()
        if cw<80 or ch<80:return
        try:
            template=self._collect_template();path=self._signature_path()
            paths=[path,self.logo_path_var.get(),self.rx_path_var.get()]
            stamps=[os.stat(p).st_mtime_ns if p and os.path.isfile(p) else None for p in paths]
            key=(json.dumps(template,sort_keys=True),path,tuple(stamps),json.dumps(get_setting("hospital",config.DEFAULT_HOSPITAL),sort_keys=True))
            if key!=self._pdf_cache_key:
                self._pdf_bytes=template_pdf_bytes(template,path);self._pdf_cache_key=key
            rw,rh=template["page_width_in"]*72,template["page_height_in"]*72
            scale=min((cw-32)/rw,(ch-32)/rh) if self.zoom_var.get()=="Fit" else float(self.zoom_var.get().rstrip("%"))/100*96/72
            self._render_scale=scale
            doc=pdfium.PdfDocument(self._pdf_bytes)
            try:
                page=doc[0]
                try:
                    bitmap=page.render(scale=scale)
                    try:picture=bitmap.to_pil().copy()
                    finally:bitmap.close()
                finally:page.close()
            finally:doc.close()
            self._pdf_photo=ImageTk.PhotoImage(picture)
        except (ValueError,KeyError,tk.TclError):
            self.status_var.set("Enter valid text sizes and choose a paper size to update the PDF.");return
        except Exception as exc:
            self.status_var.set(f"Could not render PDF view: {exc}");return
        canvas.delete("all");self._image_boxes={}
        pw,ph=picture.size;px,py=max(16,(cw-pw)/2),max(16,(ch-ph)/2)
        self._paper=(px,py,pw,ph)
        canvas.configure(scrollregion=(0,0,max(cw,pw+32),max(ch,ph+32)))
        canvas.create_image(px,py,image=self._pdf_photo,anchor="nw")
        self.signature_hint.set("Showing the assigned signature." if path and os.path.isfile(path) else "No image assigned. The signature outline is a guide only.")
        for name,key in self.IMAGE_NAMES.items():
            if not getattr(self,f"{key}_enabled_var").get():continue
            x,y,w,h=[v.get() for v in self._image_vars(key)]
            x=max(0,min(1-w,x));y=max(0,min(1-h,y))
            box=(px+x*pw,py+y*ph,px+(x+w)*pw,py+(y+h)*ph);self._image_boxes[key]=box
            if self.guides_var.get():canvas.create_rectangle(*box,outline="#2563eb" if name==self.selected_image.get() else "#94a3b8",width=2,dash=(4,2))

        if self._focus_signature and "sig" in self._image_boxes:
            x1,y1,x2,y2=self._image_boxes["sig"]
            canvas.xview_moveto(max(0,((x1+x2)/2-cw/2)/max(cw,pw+32)))
            canvas.yview_moveto(max(0,((y1+y2)/2-ch/2)/max(ch,ph+32)))
            self._focus_signature=False

    def _zoom(self,direction):
        return zoom_step(self.zoom_var,direction,getattr(self,"_render_scale",1))

    def zoom_signature(self):
        self.selected_image.set("Doctor e-signature");self.guides_var.set(True)
        self._focus_signature=True;self.zoom_var.set("200%");self._schedule_preview()

    def _horizontal_scroll(self,event):
        self.preview_canvas.xview_scroll(-int(event.delta/120)*3,"units");return "break"

    def _start_drag(self,event):
        x=self.preview_canvas.canvasx(event.x);y=self.preview_canvas.canvasy(event.y)
        for key,box in reversed(list(self._image_boxes.items())):
            if box[0]<=x<=box[2] and box[1]<=y<=box[3]:
                self.selected_image.set(next(name for name,value in self.IMAGE_NAMES.items() if value==key))
                self._drag=(key,x-box[0],y-box[1]);self.preview_canvas.configure(cursor="fleur");return

    def _drag_image(self,event):
        if not self._drag:return
        key,dx,dy=self._drag;px,py,pw,ph=self._paper
        x,y,w,h=self._image_vars(key)
        x.set(max(0,min(1-w.get(),(self.preview_canvas.canvasx(event.x)-dx-px)/pw)))
        y.set(max(0,min(1-h.get(),(self.preview_canvas.canvasy(event.y)-dy-py)/ph)))

    def _end_drag(self,event=None):
        self._drag=None;self.preview_canvas.configure(cursor="hand2");self._refresh_preview()

    def _move_image(self,dx,dy):
        x,y,w,h=self._image_vars(self.IMAGE_NAMES[self.selected_image.get()])
        x.set(max(0,min(1-w.get(),x.get()+dx)));y.set(max(0,min(1-h.get(),y.get()+dy)))

    def _resize_image(self,factor):
        x,y,w,h=self._image_vars(self.IMAGE_NAMES[self.selected_image.get()])
        factor=max(.02/min(w.get(),h.get()),min(factor,.9/max(w.get(),h.get())))
        w.set(w.get()*factor);h.set(h.get()*factor);self._move_image(0,0)

    def _place_signature(self):
        self.selected_image.set("Doctor e-signature")
        x,y,w,h=self._image_vars("sig");pw,ph=self.PAGE_PRESETS[self.page_preset_var.get()]
        margin=self.MARGIN_PRESETS[self.margin_preset_var.get()]
        x.set(max(0,min(1-w.get(),1-(margin+1.15)/pw-w.get()/2)))
        y.set(max(0,1-(.55+36/72)/ph-h.get()));self.sig_enabled_var.set(True)

    def _pick_image(self,key):
        path=filedialog.askopenfilename(title="Choose image",filetypes=[("Images","*.png *.jpg *.jpeg *.gif *.bmp")])
        if path:
            getattr(self,f"{key}_path_var").set(path);getattr(self,f"{key}_enabled_var").set(True)
            self.selected_image.set(next(name for name,value in self.IMAGE_NAMES.items() if value==key))

    def _pick_color(self):
        color=colorchooser.askcolor(color=self.accent_var.get(),title="Choose text color")[1]
        if color:self.accent_var.set(color)

    def _collect_template(self):
        template=copy.deepcopy(get_setting("template",config.DEFAULT_TEMPLATE) or config.DEFAULT_TEMPLATE)
        template["page_width_in"],template["page_height_in"]=self.PAGE_PRESETS[self.page_preset_var.get()]
        template.update(margin_in=self.MARGIN_PRESETS[self.margin_preset_var.get()],header_font_size=self.header_font_var.get(),
            body_font_size=self.body_font_var.get(),accent_color=self.accent_var.get(),show_motto=self.show_motto_var.get(),transparent_images=self.transparent_images_var.get())
        for key,cfg_key in [("sig","signature_img"),("logo","logo"),("rx","rx_symbol")]:
            cfg=copy.deepcopy(template.get(cfg_key,{}));x,y,w,h=[v.get() for v in self._image_vars(key)]
            x=max(0,min(1-w,x));y=max(0,min(1-h,y))
            cfg.update(x_pct=x,y_pct=1-y-h if key=="sig" else y,w_pct=w,h_pct=h)
            if key=="sig":cfg["show_assigned"]=self.sig_enabled_var.get()
            else:cfg.update(enabled=getattr(self,f"{key}_enabled_var").get(),path=getattr(self,f"{key}_path_var").get())
            template[cfg_key]=cfg
        template["show_rx_symbol"]=self.rx_enabled_var.get();template["rx_symbol_path"]=self.rx_path_var.get()
        return template

    def _persist_template(self,*,show_message=False):
        try:
            template=self._collect_template()
            if not 6<=template["header_font_size"]<=30 or not 6<=template["body_font_size"]<=22:
                raise ValueError("Use text sizes from 6 to 30 for the hospital name, and 6 to 22 for medicines.")
            set_setting("template",template)
        except Exception as exc:
            messagebox.showerror("Cannot save layout",f"Please check your settings.\n{exc}");return None
        self.template=template;self.dirty=False;self.status_var.set("Layout saved. New records will use it.")
        if show_message:messagebox.showinfo("Layout saved","Your layout will be used for new prescriptions.")
        return template

    def _save_template(self):
        self._persist_template(show_message=False)

    def _preview_pdf(self):
        try:
            template=self._collect_template()
            open_file(generate_template_preview(self._signature_path(),template))
        except Exception as exc:messagebox.showerror("Print preview",str(exc))

    def _preview_print(self):
        self._preview_pdf()

    def _reset_defaults(self):
        if not messagebox.askyesno("Restore defaults?","Restore the original layout? Click Save layout to keep it."):return
        defaults=copy.deepcopy(config.DEFAULT_TEMPLATE)
        defaults["rx_symbol"]={"enabled":True,"path":defaults.get("rx_symbol_path",""),"x_pct":.07,"y_pct":.30,"w_pct":.10,"h_pct":.08}
        self._load_variables(defaults)
        self.paper_picker["values"]=list(self.PAGE_PRESETS);self.margin_picker["values"]=list(self.MARGIN_PRESETS)
        self.status_var.set("Defaults restored. Click Save layout to keep them.")
