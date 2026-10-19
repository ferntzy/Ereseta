"""Common controls and wording for prescription and OPD layout editors."""
from tkinter import ttk
ZOOM_LEVELS=['Fit','25%','50%','75%','100%','125%','150%','200%','250%','300%']
PAPER_PRESETS={'Prescription (5.5 x 8.5 in)':(5.5,8.5),'Short bond (8.5 x 11 in)':(8.5,11),'A4 (8.27 x 11.69 in)':(8.27,11.69),'Long bond (8.5 x 13 in)':(8.5,13),'A5 (5.83 x 8.27 in)':(5.83,8.27)}

def zoom_step(variable,direction,scale):
    current=scale*75 if variable.get()=='Fit' else float(variable.get().rstrip('%'))
    levels=[float(z.rstrip('%')) for z in ZOOM_LEVELS[1:]]
    candidates=[z for z in levels if z>current] if direction>0 else [z for z in levels if z<current]
    value=(min(candidates) if direction>0 else max(candidates)) if candidates else max(25,min(300,current))
    variable.set(f'{value:g}%')
    return 'break'

def preview_toolbar(parent,zoom,step,signature):
    bar=ttk.Frame(parent,style='Card.TFrame')
    ttk.Button(bar,text='-',width=3,command=lambda:step(-1)).pack(side='left')
    ttk.Combobox(bar,textvariable=zoom,values=ZOOM_LEVELS,state='readonly',width=6).pack(side='left',padx=4)
    ttk.Button(bar,text='+',width=3,command=lambda:step(1)).pack(side='left')
    ttk.Button(bar,text='Fit page',command=lambda:zoom.set('Fit')).pack(side='left',padx=6)
    ttk.Button(bar,text='Zoom to signature',command=signature).pack(side='left')
    return bar


def settings_notebook(parent):
    style=ttk.Style(parent)
    style.configure('Settings.TNotebook.Tab',padding=[8,6],font=('Segoe UI',9,'bold'))
    return ttk.Notebook(parent,style='Settings.TNotebook')
