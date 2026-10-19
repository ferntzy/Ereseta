"""Plain-language OPD template controls with a production PDF preview."""
import copy
import os
import datetime
import tkinter as tk
from tkinter import ttk,messagebox
from PIL import ImageTk
import pypdfium2 as pdfium
from . import config
from .layout_controls import PAPER_PRESETS, preview_toolbar, zoom_step, settings_notebook
from .database import get_setting,get_all_physicians,get_conn
from .opd_layout import DEFAULT_OPD_LAYOUT,validate_layout,signature_box
from .opd_pdf import opd_pdf_bytes
from .pdf_generator import open_file
from contextlib import closing
import json

class OPDLayoutEditor(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=10,style="Card.TFrame")
        self.app=app;self.job=None;self.photo=None;self.dirty=False
        self.drag=None;self.signature_bounds=None;self.focus_signature=False
        self.columnconfigure(1,weight=1);self.rowconfigure(1,weight=1)
        ttk.Label(self,text='OPD sheet layout',font=('Segoe UI',15,'bold')).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,8))
        groups=settings_notebook(self);groups.grid(row=1,column=0,sticky='ns',padx=(0,15))
        controls=ttk.Frame(groups,padding=8,style="Card.TFrame");groups.add(controls,text='Paper & text')
        self.values={}
        self.preview_doctor=tk.StringVar(value="Current record doctor")
        self.guides=tk.BooleanVar(value=True)
        saved=validate_layout(get_setting('opd_layout',{}));page=get_setting('opd_page',dict(width=8.5,height=11))
        self.values['signature_height']=tk.StringVar(value=str(saved['signature_height']))
        self.signature_position={key:saved[key] for key in ('signature_x','signature_y')}
        fields=[('title','Sheet title',saved['title']),('width','Paper width (inches)',page['width']),('height','Paper height (inches)',page['height']),('margin','Page margins (inches)',saved['margin']),('body_size','Notes text size',saved['body_size']),('header_size','Hospital name size',saved['header_size'])]
        self.paper_preset=tk.StringVar(value=next((n for n,v in PAPER_PRESETS.items() if v==(page['width'],page['height'])),'Custom'))
        ttk.Label(controls,text='Paper size',style='FormLabel.TLabel').grid(row=0,column=0,sticky='w')
        preset=ttk.Combobox(controls,textvariable=self.paper_preset,values=[*PAPER_PRESETS,'Custom'],state='readonly',width=25)
        preset.grid(row=1,column=0,sticky='ew');preset.bind('<<ComboboxSelected>>',self.apply_paper)
        for row,(key,label,value) in enumerate(fields,start=1):
            ttk.Label(controls,text=label,style='FormLabel.TLabel').grid(row=row*2,column=0,sticky='w',pady=(4,1))
            var=tk.StringVar(value=str(value));self.values[key]=var
            ttk.Entry(controls,textvariable=var,width=25).grid(row=row*2+1,column=0,sticky='ew')
        controls=ttk.Frame(groups,padding=8,style="Card.TFrame");groups.add(controls,text='Sections')
        row=0
        self.space_options={'Small':12,'Standard':18,'Large':30,'Extra large':46}
        for key,label in [('s_weight','Subjective space'),('o_weight','Objective space'),('a_weight','Assessment space'),('p_weight','Plan space')]:
            ttk.Label(controls,text=label,style='FormLabel.TLabel').grid(row=row,column=0,sticky='w',pady=(4,1));row+=1
            name=min(self.space_options,key=lambda n:abs(self.space_options[n]-saved[key]))
            var=tk.StringVar(value=name);self.values[key]=var
            ttk.Combobox(controls,textvariable=var,values=list(self.space_options),state='readonly',width=23).grid(row=row,column=0,sticky='ew');row+=1
        controls=ttk.Frame(groups,padding=8,style="Card.TFrame");groups.add(controls,text='Pictures & signature')
        ttk.Label(controls,text='Preview signature from',style='FormLabel.TLabel').grid(row=0,column=0,sticky='w')
        self.doctor_picker=ttk.Combobox(controls,textvariable=self.preview_doctor,state='readonly',postcommand=self.refresh_doctors,width=25)
        self.doctor_picker.grid(row=1,column=0,sticky='ew');self.refresh_doctors()
        buttons=ttk.Frame(controls,style='Card.TFrame');buttons.grid(row=2,column=0,sticky='ew',pady=8)
        for label,factor in [('Smaller',.9),('Bigger',1.1)]:ttk.Button(buttons,text=label,command=lambda f=factor:self.resize_signature(f)).pack(side='left',expand=True,fill='x')
        arrows=ttk.Frame(controls,style='Card.TFrame');arrows.grid(row=3,column=0,sticky='ew')
        for label,x,y in [('Left',-.01,0),('Up',0,-.01),('Down',0,.01),('Right',.01,0)]:ttk.Button(arrows,text=label,width=5,command=lambda dx=x,dy=y:self.nudge_signature(dx,dy)).pack(side='left',expand=True,fill='x')
        ttk.Button(controls,text="Put signature above doctor's name",command=self.reset_signature).grid(row=4,column=0,sticky='ew',pady=8)
        row=5
        for key,label,options in [('doctor_position','Doctor / signature position',['Left','Center','Right']),('signature_width','Signature width (points)',None)]:
            ttk.Label(controls,text=label,style='FormLabel.TLabel').grid(row=row,column=0,sticky='w',pady=(4,1));row+=1
            var=tk.StringVar(value=str(saved[key]));self.values[key]=var
            widget=ttk.Combobox(controls,textvariable=var,values=options,state='readonly',width=23) if options else ttk.Entry(controls,textvariable=var)
            widget.grid(row=row,column=0,sticky='ew');row+=1
        for key,label in [('show_logo','Show hospital logo'),('show_motto','Show hospital motto')]:
            var=tk.BooleanVar(value=saved[key]);self.values[key]=var
            ttk.Checkbutton(controls,text=label,variable=var).grid(row=row,column=0,sticky='w',pady=4);row+=1
        viewer=ttk.Frame(self,style="Card.TFrame");viewer.grid(row=1,column=1,sticky='nsew');viewer.columnconfigure(0,weight=1);viewer.rowconfigure(2,weight=1)
        self.zoom=tk.StringVar(value='Fit')
        bar=preview_toolbar(viewer,self.zoom,self.zoom_step,self.zoom_signature)
        bar.grid(row=0,column=0,columnspan=2,sticky='ew')
        ttk.Checkbutton(viewer,text='Show drag outlines (not printed)',variable=self.guides).grid(row=1,column=0,columnspan=2,sticky='w',pady=4)
        self.canvas=tk.Canvas(viewer,bg='#dce3eb',highlightthickness=0,width=420,height=500,yscrollincrement=20)
        self.canvas.grid(row=2,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(viewer,command=self.canvas.yview);scroll.grid(row=2,column=1,sticky='ns');self.canvas.configure(yscrollcommand=scroll.set)
        horizontal=ttk.Scrollbar(viewer,orient='horizontal',command=self.canvas.xview);horizontal.grid(row=3,column=0,sticky='ew');self.canvas.configure(xscrollcommand=horizontal.set)
        self.canvas.bind('<ButtonPress-1>',self.start_drag)
        self.canvas.bind('<B1-Motion>',self.move_drag)
        self.canvas.bind('<ButtonRelease-1>',self.end_drag)
        self.canvas.bind('<Motion>',self.hover_signature)
        self.canvas.bind('<Control-MouseWheel>',lambda e:self.zoom_step(1 if e.delta>0 else -1))
        self.canvas.bind('<Shift-MouseWheel>',self.horizontal_scroll)
        self.status=tk.StringVar(value='Changes apply to new OPD records after Save layout.')
        ttk.Label(self,textvariable=self.status,style='Hint.TLabel',wraplength=600).grid(row=2,column=0,columnspan=2,sticky='w',pady=8)
        buttons=ttk.Frame(self,style="Card.TFrame");buttons.grid(row=3,column=0,columnspan=2,sticky='ew')
        ttk.Button(buttons,text='Restore defaults',command=self.defaults).pack(side='left')
        ttk.Button(buttons,text='Save layout',command=self.save,style='Accent.TButton').pack(side='right')
        ttk.Button(buttons,text='Print preview',command=self.print_preview).pack(side='right',padx=6)
        self.preview_doctor.trace_add('write',self.schedule);self.guides.trace_add('write',self.schedule)
        for var in self.values.values():var.trace_add('write',self.changed)
        self.values['doctor_position'].trace_add('write',self.reset_signature)
        for key in ('width','height'):self.values[key].trace_add('write',self.sync_paper)
        self.zoom.trace_add('write',self.schedule);self.canvas.bind('<Configure>',self.schedule)
        self.bind('<Destroy>',self.closed);self.schedule()

    def collect(self):
        values={key:var.get() for key,var in self.values.items()}
        page={key:float(values.pop(key)) for key in ('width','height')}
        if not 5<=page['width']<=14 or not 7<=page['height']<=17:raise ValueError('Paper must be 5-14 inches wide and 7-17 inches high.')
        for key in ('s_weight','o_weight','a_weight','p_weight'):values[key]=self.space_options[values[key]]
        values.update(self.signature_position)
        return validate_layout(values),page

    def sample(self,layout,page):
        self.refresh_doctors()
        name=self.app.opd_editor.doctor.get() if self.preview_doctor.get()=='Current record doctor' else self.preview_doctor.get()
        from .database import ensure_dr_prefix
        doctor=self.doctors.get(ensure_dr_prefix(name),dict(name=name or 'Dr. Sample Physician'))
        return dict(patient=dict(first_name='Sample',last_name='Patient',age=30,address='Sample address'),date=datetime.date.today().isoformat(),hospital_no='SAMPLE-001',physician=doctor,include_signature=bool(doctor.get('signature_path') and os.path.isfile(doctor['signature_path'])),
            soap=dict(S='Patient concerns and symptoms.',O='Examination findings.',A='Assessment.',P='Treatment, advice and follow-up.'),page=page,opd_layout=layout,hospital=get_setting('hospital',config.DEFAULT_HOSPITAL),template=get_setting('template',config.DEFAULT_TEMPLATE))

    def changed(self,*_):
        self.dirty=True;self.schedule()

    def schedule(self,*_):
        if self.job:self.after_cancel(self.job)
        self.job=self.after(250,self.render)

    def render(self):
        self.job=None
        try:
            layout,page=self.collect();data=opd_pdf_bytes(self.sample(layout,page))
            document=pdfium.PdfDocument(data)
            try:
                first=document[0]
                try:
                    w,h=first.get_size();scale=min(max(180,self.canvas.winfo_width()-28)/w,max(300,self.canvas.winfo_height()-28)/h) if self.zoom.get()=='Fit' else float(self.zoom.get().rstrip('%'))/100*96/72
                    bitmap=first.render(scale=scale)
                    try:im=bitmap.to_pil().copy()
                    finally:bitmap.close()
                finally:first.close()
            finally:document.close()
            self.photo=ImageTk.PhotoImage(im);self.canvas.delete('all')
            self.origin=(max(14,(self.canvas.winfo_width()-im.width)/2),14)
            self.scale=scale;self.page_size=(w,h)
            self.canvas.create_image(*self.origin,image=self.photo,anchor='nw')
            total_w=max(self.canvas.winfo_width(),im.width+28);total_h=max(self.canvas.winfo_height(),im.height+28)
            self.canvas.configure(scrollregion=(0,0,total_w,total_h))
            sx,sy,sw,sh=signature_box(layout,w,h)
            x,y=self.origin[0]+sx*scale,self.origin[1]+sy*scale
            self.signature_bounds=(x,y,x+sw*scale,y+sh*scale)
            if self.guides.get():self.canvas.create_rectangle(*self.signature_bounds,outline='#2563eb',width=2,dash=(5,3),tags='signature-guide')
            if self.guides.get():self.canvas.create_text(x,y-4,text='Drag signature',anchor='sw',fill='#173b63',tags='signature-guide')
            if self.focus_signature:
                self.canvas.xview_moveto(max(0,(x+sw*scale/2-self.canvas.winfo_width()/2)/total_w))
                self.canvas.yview_moveto(max(0,(y+sh*scale/2-self.canvas.winfo_height()/2)/total_h))
                self.focus_signature=False
            self.status.set('Unsaved layout changes.' if self.dirty else 'Drag the blue signature outline, then Save layout. Guides do not print.')
        except Exception as exc:self.status.set(f'Check settings: {exc}')

    def save(self):
        try:
            layout,page=self.collect();opd_pdf_bytes(self.sample(layout,page))
            with closing(get_conn()) as conn,conn:
                for key,value in [('opd_layout',layout),('opd_page',page)]:conn.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(key,json.dumps(value)))
            self.app.opd_editor.width.set(str(page['width']));self.app.opd_editor.height.set(str(page['height']))
            self.dirty=False;self.status.set('OPD layout saved. New previews and records will use it.')
        except Exception as exc:messagebox.showwarning('Check OPD layout',str(exc))

    def defaults(self):
        if not messagebox.askyesno("Restore defaults?","Restore the original layout? Click Save layout to keep it."):return
        self.signature_position={'signature_x':None,'signature_y':None}
        for key,value in DEFAULT_OPD_LAYOUT.items():
            if key not in self.values:continue
            self.values[key].set(next((n for n,w in self.space_options.items() if w==value),'Standard') if key.endswith('_weight') else value)
        self.values['width'].set('8.5');self.values['height'].set('11')

    def refresh_doctors(self):
        self.doctors={row['name']:dict(row) for row in get_all_physicians()}
        self.doctor_picker['values']=['Current record doctor',*self.doctors]

    def sync_paper(self,*_):
        try:dimensions=(float(self.values['width'].get()),float(self.values['height'].get()))
        except ValueError:dimensions=None
        self.paper_preset.set(next((name for name,size in PAPER_PRESETS.items() if size==dimensions),'Custom'))

    def apply_paper(self,event=None):
        name=self.paper_preset.get()
        if name in PAPER_PRESETS:
            w,h=PAPER_PRESETS[name];self.values['width'].set(str(w));self.values['height'].set(str(h))

    def zoom_step(self,direction):
        return zoom_step(self.zoom,direction,getattr(self,'scale',1))

    def horizontal_scroll(self,event):
        self.canvas.xview_scroll(-int(event.delta/120)*3,'units');return 'break'

    def nudge_signature(self,dx,dy):
        layout,page=self.collect();w,h=page['width']*72,page['height']*72
        x,y,sw,sh=signature_box(layout,w,h)
        self.signature_position=dict(signature_x=max(0,min(w-sw,x+dx*w))/w,signature_y=max(0,min(h-sh,y+dy*h))/h)
        self.changed()

    def resize_signature(self,factor):
        w=float(self.values['signature_width'].get());h=float(self.values['signature_height'].get())
        factor=max(90/w,20/h,min(factor,190/w,90/h))
        self.values['signature_width'].set(str(w*factor));self.values['signature_height'].set(str(h*factor))

    def print_preview(self):
        try:
            layout,page=self.collect();data=opd_pdf_bytes(self.sample(layout,page))
            path=os.path.join(config.OUTPUT_DIR,'OPD_Template_Preview.pdf')
            with open(path,'wb') as output:output.write(data)
            open_file(path)
        except Exception as exc:messagebox.showerror('Print preview',str(exc))

    def reset_signature(self,*_):
        self.signature_position={'signature_x':None,'signature_y':None}
        self.changed()

    def zoom_signature(self):
        self.guides.set(True);self.focus_signature=True;self.zoom.set('200%');self.schedule()

    def hit_signature(self,event):
        if not self.signature_bounds:return False
        x,y=self.canvas.canvasx(event.x),self.canvas.canvasy(event.y)
        left,top,right,bottom=self.signature_bounds
        return left<=x<=right and top<=y<=bottom

    def hover_signature(self,event):
        self.canvas.configure(cursor='fleur' if self.hit_signature(event) else '')

    def start_drag(self,event):
        if self.hit_signature(event):
            if self.job:self.after_cancel(self.job);self.job=None
            x,y=self.canvas.canvasx(event.x),self.canvas.canvasy(event.y)
            self.drag=(x-self.signature_bounds[0],y-self.signature_bounds[1])
            self.canvas.configure(cursor='fleur')

    def move_drag(self,event):
        if self.drag is None:return
        w,h=self.page_size;scale=self.scale
        old=self.signature_bounds
        sw,sh=(old[2]-old[0])/scale,(old[3]-old[1])/scale
        x=(self.canvas.canvasx(event.x)-self.drag[0]-self.origin[0])/scale
        y=(self.canvas.canvasy(event.y)-self.drag[1]-self.origin[1])/scale
        x=max(0,min(w-sw,x));y=max(0,min(h-sh,y))
        self.signature_position=dict(signature_x=x/w,signature_y=y/h)
        nx,ny=self.origin[0]+x*scale,self.origin[1]+y*scale
        self.canvas.move('signature-guide',nx-old[0],ny-old[1])
        self.signature_bounds=(nx,ny,nx+sw*scale,ny+sh*scale)
        self.dirty=True;self.status.set('Signature moved. Save OPD layout to keep this position.')

    def end_drag(self,event):
        if self.drag is not None:
            self.move_drag(event);self.drag=None;self.canvas.configure(cursor='');self.schedule()

    def closed(self,event):
        if event.widget is self and self.job:self.after_cancel(self.job);self.job=None
