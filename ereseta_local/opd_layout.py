"""Independent, validated OPD layout settings."""
import math
DEFAULT_OPD_LAYOUT = dict(title='OPD RECORD SHEET',margin=0.45,body_size=10,header_size=13,
    show_logo=True,show_motto=True,s_weight=18,o_weight=18,a_weight=18,p_weight=46,
    doctor_position='Right',signature_width=150,signature_height=45,signature_x=None,signature_y=None)

def validate_layout(value):
    layout={**DEFAULT_OPD_LAYOUT,**value}
    layout['title']=str(layout['title']).strip()
    if not layout['title'] or len(layout['title'])>45:raise ValueError('Use a sheet title between 1 and 45 characters.')
    for key,low,high in [('margin',.25,.7),('body_size',8,14),('header_size',10,18),('signature_width',90,190),('signature_height',20,90),*[(k,10,60) for k in ('s_weight','o_weight','a_weight','p_weight')]]:
        layout[key]=float(layout[key])
        if not math.isfinite(layout[key]) or not low<=layout[key]<=high:raise ValueError(f'Please check {key.replace("_"," ")} ({low}-{high}).')
    if layout['doctor_position'] not in ('Left','Center','Right'):raise ValueError('Choose a doctor position.')
    for key in ('signature_x','signature_y'):
        if layout[key] is not None:
            layout[key]=float(layout[key])
            if not math.isfinite(layout[key]) or not 0<=layout[key]<=1:raise ValueError('Signature position must be on the page.')
    return layout


def signature_box(layout,width,height):
    """Shared PDF/editor rectangle, in points measured from the page top."""
    margin=layout['margin']*72
    center={'Left':margin+105,'Center':width/2,'Right':width-margin-105}[layout['doctor_position']]
    w,h=layout['signature_width'],layout['signature_height']
    x=center-w/2 if layout['signature_x'] is None else layout['signature_x']*width
    y=height-margin-27-h if layout['signature_y'] is None else layout['signature_y']*height
    return max(0,min(width-w,x)),max(0,min(height-h,y)),w,h
