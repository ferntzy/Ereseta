"""Staff-facing OPD editor, using shared patients, hospital settings and PDF review."""
import datetime
import json
import os
import tkinter as tk
from tkinter import ttk, messagebox
from . import config, theme
from .database import get_all_patients, get_setting, full_name, parse_birthday, get_all_physicians, ensure_dr_prefix
from .opd_database import save_opd, list_opd, get_opd, export_opd
from .opd_pdf import opd_pdf_bytes
from .pdf_generator import open_file
from .prescription_preview import PrescriptionPreview
from .widgets import AutocompleteCombobox, DateEntry


class OPDEditor(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent)
        self.app=app
        self.patients={}
        self.fields={}
        self.paper=get_setting('opd_page',{'width':8.5,'height':11})
        self.status=tk.StringVar(value='Choose a saved patient or enter a new patient. Then complete the SOAP sections.')
        intro=ttk.Frame(self,style='Card.TFrame',padding=14);intro.pack(fill='x',padx=8,pady=8)
        ttk.Label(intro,text='OPD record sheet',font=('Segoe UI',16,'bold')).pack(anchor='w')
        ttk.Label(intro,text='One visit, one SOAP table. Longer notes expand automatically onto continuation pages.',style='Hint.TLabel',wraplength=740).pack(anchor='w',pady=(4,0))
        toolbar=ttk.Frame(intro,style='Card.TFrame');toolbar.pack(fill='x',pady=(10,0))
        ttk.Button(toolbar,text='Use prescription patient',command=self.use_rx_patient).pack(side='left',padx=8)
        patient=ttk.LabelFrame(self,text='  1  Patient & visit  ');patient.pack(fill='x',padx=8,pady=8)
        for col in range(3):patient.columnconfigure(col,weight=1,uniform='opd')
        ttk.Label(patient,text='Find a saved patient',style='FormLabel.TLabel').grid(row=0,column=0,columnspan=3,sticky='w')
        self.picker=AutocompleteCombobox(patient,auto_dropdown=True)
        self.picker.grid(row=1,column=0,columnspan=3,sticky='ew',pady=(3,8))
        self.picker.bind('<<ComboboxSelected>>',self.pick_patient)
        self.picker.bind('<FocusIn>',lambda e:self.refresh_patients(),add='+')
        for key,label,row,col in [('first_name','First name *',2,0),('middle_name','Middle name',2,1),('last_name','Last name *',2,2),('age','Age in years *',4,0),('hospital_no','Hospital number (optional)',4,1),('address','Address / barangay',6,0)]:
            ttk.Label(patient,text=label,style='FormLabel.TLabel').grid(row=row,column=col,sticky='w',padx=5)
            entry=ttk.Entry(patient,width=16);entry.grid(row=row+1,column=col,columnspan=3 if key=='address' else 1,sticky='ew',padx=5,pady=(3,9));self.fields[key]=entry
        ttk.Label(patient,text='Visit date *',style='FormLabel.TLabel').grid(row=4,column=2,sticky='w',padx=5)
        self.date=DateEntry(patient,default=datetime.date.today(),width=12);self.date.grid(row=5,column=2,sticky='ew',padx=5,pady=(3,9))
        doctor=ttk.LabelFrame(self,text='  Doctor & optional signature  ');doctor.pack(fill='x',padx=8,pady=8)
        ttk.Label(doctor,text='Doctor name *',style='FormLabel.TLabel').pack(anchor='w')
        self.doctor=AutocompleteCombobox(doctor,auto_dropdown=True);self.doctor.pack(fill='x',pady=6)
        self.doctor.bind('<FocusIn>',lambda e:self.refresh_doctors(),add='+')
        self.include_signature=tk.BooleanVar(value=False)
        ttk.Checkbutton(doctor,text="Include doctor's saved signature (optional)",variable=self.include_signature).pack(anchor='w')
        ttk.Label(doctor,text='Signatures are assigned to doctors on the New Prescription tab.',style='Hint.TLabel').pack(anchor='w',pady=(4,0))
        self.refresh_doctors()
        paper=ttk.LabelFrame(self,text='Paper')  # Paper controls now live in Layouts; preserve variables for drafts.
        self.paper_choice=tk.StringVar(value='Custom')
        presets={'Short bond (8.5 x 11 in)':(8.5,11),'A4 (8.27 x 11.69 in)':(8.27,11.69),'Long bond (8.5 x 13 in)':(8.5,13),'Custom':None}
        for name,dimensions in presets.items():
            if dimensions==(self.paper['width'],self.paper['height']):self.paper_choice.set(name)
        choice=ttk.Combobox(paper,textvariable=self.paper_choice,values=list(presets),state='readonly',width=26);choice.grid(row=0,column=0,padx=5,sticky='w')
        self.width=tk.StringVar(value=str(self.paper['width']));self.height=tk.StringVar(value=str(self.paper['height']))
        ttk.Label(paper,text='Width (in)').grid(row=0,column=1,padx=(12,3));ttk.Entry(paper,textvariable=self.width,width=6).grid(row=0,column=2)
        ttk.Label(paper,text='Height (in)').grid(row=0,column=3,padx=(12,3));ttk.Entry(paper,textvariable=self.height,width=6).grid(row=0,column=4)
        def preset(event):
            name=self.paper_choice.get();dimensions=presets[name]
            if dimensions:
                self.width.set(str(dimensions[0]));self.height.set(str(dimensions[1]));self.paper_choice.set(name)
        choice.bind('<<ComboboxSelected>>',preset)
        for variable in (self.width,self.height):variable.trace_add('write',lambda *_:self.paper_choice.set('Custom'))
        ttk.Label(paper,text='Applies to OPD sheets only. The hospital header comes from your existing settings.',style='Hint.TLabel',wraplength=700).grid(row=1,column=0,columnspan=5,sticky='w',padx=5,pady=(8,0))
        self.soap={}
        self.soap_tabs=ttk.Notebook(self);self.soap_tabs.pack(fill="both",expand=True,padx=8,pady=12)
        self.soap_panels={}
        for key,title,hint,lines in [('S','Subjective','Patient concerns, symptoms and history.',5),('O','Objective','Examination findings, observations and results.',5),('A','Assessment','Assessment or diagnosis.',5),('P','Plan','Treatment plan, advice, tests and follow-up.',9)]:
            section=ttk.Frame(self.soap_tabs,padding=12,style="Card.TFrame");self.soap_tabs.add(section,text=f'{key}  {title}');self.soap_panels[key]=section
            ttk.Label(section,text=hint,style='Hint.TLabel').pack(anchor='w',pady=(0,6))
            row=ttk.Frame(section,style='Card.TFrame');row.pack(fill='both',expand=True)
            text=tk.Text(row,height=12,wrap='word',font=('Segoe UI',11),undo=True,padx=10,pady=10,relief='solid',bd=1,highlightthickness=1,highlightbackground=theme.COLOR_BORDER,highlightcolor=theme.COLOR_ACCENT)
            text.pack(side='left',fill='both',expand=True)
            scroll=ttk.Scrollbar(row,command=text.yview);scroll.pack(side='right',fill='y');text.configure(yscrollcommand=scroll.set)
            self.soap[key]=text
        self.refresh_patients()

    def open_layout(self):
        self.app.notebook.select(self.app.template_tab)
        self.app.layout_tabs.select(self.app.opd_layout_panel)

    def refresh_doctors(self):
        self.doctors={row['name']:dict(row) for row in get_all_physicians()}
        self.doctor.set_completion_list(sorted(self.doctors))

    def refresh_patients(self):
        self.patients={full_name(row):dict(row) for row in get_all_patients()}
        self.picker.set_completion_list(sorted(self.patients))

    def fill_patient(self,patient):
        for key in ('first_name','middle_name','last_name','age','address'):
            entry=self.fields[key];entry.delete(0,'end');entry.insert(0,str(patient.get(key) if patient.get(key) is not None else ''))

    def pick_patient(self,event=None):
        patient=self.patients.get(self.picker.get())
        if patient:
            self.fill_patient(patient)
            self.fields['hospital_no'].delete(0,'end')

    def use_rx_patient(self):
        if any(e.get().strip() for e in self.fields.values()) and not messagebox.askyesno('Replace patient details?','Replace this OPD patient with the patient on the prescription form? Your SOAP notes will remain.'):
            return
        self.fill_patient(dict(first_name=self.app.p_first.get(),middle_name=self.app.p_middle.get(),last_name=self.app.p_last.get(),age=self.app.p_age.get(),address=self.app.p_address.get()))
        self.fields['hospital_no'].delete(0,'end');self.picker.set('')

    def has_draft(self):
        return bool(self.doctor.get().strip() or self.include_signature.get()) or any(e.get().strip() for e in self.fields.values()) or any(t.get('1.0','end-1c').strip() for t in self.soap.values())

    def clear(self,confirm=True):
        if confirm and self.has_draft() and not messagebox.askyesno('Start a new OPD record?','Discard the unfinished OPD record?'):return
        for e in self.fields.values():e.delete(0,'end')
        for t in self.soap.values():t.delete('1.0','end')
        self.picker.set('');self.date.set(datetime.date.today())
        self.doctor.set('');self.include_signature.set(False)

    def collect(self):
        patient={key:self.fields[key].get().strip() for key in ('first_name','middle_name','last_name','age','address')}
        for key in ('first_name','last_name','age'):
            if not patient[key]:
                self.focus_field(self.fields[key]);raise ValueError('Enter the patient first name, last name and age.')
        if not patient['age'].isascii() or not patient['age'].isdigit() or not 0<=int(patient['age'])<=130:
            self.focus_field(self.fields['age']);raise ValueError('Enter age in whole years from 0 to 130.')
        patient['age']=int(patient['age'])
        date=parse_birthday(self.date.get())
        if not date:raise ValueError('Enter a valid visit date (MM/DD/YYYY).')
        width,height=float(self.width.get()),float(self.height.get())
        if not 5<=width<=14 or not 7<=height<=17:raise ValueError('Paper width must be 5-14 inches and height 7-17 inches.')
        name=ensure_dr_prefix(self.doctor.get().strip()) if self.doctor.get().strip() else ''
        if not name:
            self.focus_field(self.doctor);raise ValueError('Choose or enter the doctor name.')
        self.refresh_doctors()
        physician=dict(self.doctors.get(name,{}));physician['name']=name
        signature=physician.get('signature_path','') or ''
        if self.include_signature.get() and (not signature or not os.path.isfile(signature)):
            raise ValueError('This doctor has no available saved signature. Assign one on New Prescription, or uncheck Include signature.')
        return dict(opd_layout=get_setting("opd_layout",{}),physician=physician,include_signature=self.include_signature.get(),patient=patient,hospital_no=self.fields['hospital_no'].get().strip(),date=date.isoformat(),
                    soap={k:t.get('1.0','end-1c') for k,t in self.soap.items()},page=dict(width=width,height=height),
                    hospital=get_setting('hospital',config.DEFAULT_HOSPITAL),template=get_setting('template',config.DEFAULT_TEMPLATE))

    def focus_field(self,field):
        for key,text in self.soap.items():
            if text is field:self.soap_tabs.select(self.soap_panels[key])
        canvas=self.app._page_canvases[str(self.app.opd_tab)];self.update_idletasks()
        y=field.winfo_rooty()-canvas.winfo_rooty()+canvas.canvasy(0)-60
        region=canvas.bbox('all')
        if region:canvas.yview_moveto(max(0,y/max(1,region[3])))
        field.focus_set()

    def preview(self):
        try:
            draft=self.collect();pdf=opd_pdf_bytes(draft)
        except Exception as exc:
            messagebox.showwarning('Check OPD record',str(exc));return
        self.preview_window=PrescriptionPreview(self.app,pdf,lambda:self.save(draft,pdf),
            title='Review OPD record - not saved yet',hint='Check patient details and all SOAP pages before saving.',save_label='Save OPD record')

    def save(self,draft,pdf):
        record_id=save_opd(draft,pdf)
        self.app._refresh_caches();self.refresh_patients();self.clear(confirm=False);self.app._refresh_history()
        self.status.set(f'OPD record #{record_id} saved. Find it in History.')
        try:
            path=export_opd(record_id)
        except Exception as exc:
            messagebox.showwarning('Record saved',f'The record is saved, but its PDF could not be written: {exc}. Open it from History to try again.')
            return True
        if messagebox.askyesno('OPD record saved',f'OPD record #{record_id} and its printable PDF are saved. Open the printable copy now?'):
            try:open_file(path)
            except Exception as exc:messagebox.showwarning("PDF saved",f"The printable PDF is saved, but could not be opened: {exc}")
        return True

    def show_history(self):
        self.app._clear_history_filters()
        self.app.history_type.set('OPD');self.app._refresh_history()
        self.app.notebook.select(self.app.history_tab)

    def reuse_record(self,record_id):
        if self.has_draft() and not messagebox.askyesno('Replace draft?','Replace the unfinished OPD record with a copy of this record?'):return
        draft=json.loads(get_opd(record_id)['payload']);self.clear(confirm=False);self.fill_patient(draft['patient'])
        self.fields['hospital_no'].insert(0,draft['hospital_no'])
        for key,text in draft['soap'].items():self.soap[key].insert('1.0',text)
        self.width.set(str(draft['page']['width']));self.height.set(str(draft['page']['height']))
        self.doctor.set(draft.get('physician',{}).get('name',''))
        # Signing a new visit requires a fresh explicit choice.
        self.include_signature.set(False)
        self.status.set('Copied as a new visit dated today. Review and save to create a separate record.')
        self.app.notebook.select(self.app.opd_tab)
