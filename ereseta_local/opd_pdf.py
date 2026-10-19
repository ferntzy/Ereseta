"""Flowing OPD sheet: one SOAP table; oversized sections continue safely."""
import io
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from .opd_layout import validate_layout, signature_box
from .pdf_generator import _secure_canvas, _resolve_asset_path, _asset_reader


def opd_pdf_bytes(draft):
    width, height = float(draft['page']['width'])*72, float(draft['page']['height'])*72
    if not 5 <= width/72 <= 14 or not 7 <= height/72 <= 17:
        raise ValueError('Paper width must be 5-14 inches and height 7-17 inches.')
    layout=validate_layout(draft.get("opd_layout",{}))
    margin = layout["margin"]*72
    hospital, template = draft['hospital'], draft['template']
    patient = draft['patient']
    accent = colors.HexColor(template.get('accent_color','#173b63'))
    body = layout['body_size']
    style = ParagraphStyle('opd',fontName='Helvetica',fontSize=body,leading=body*1.35,splitLongWords=True)
    header_style = ParagraphStyle('header',fontName='Helvetica-Bold',fontSize=layout['header_size'],leading=layout['header_size']+3,alignment=1,textColor=accent)
    detail_style = ParagraphStyle('details',fontName='Helvetica',fontSize=8,leading=10,alignment=1)
    output=io.BytesIO(); c=_secure_canvas(output,(width,height)); page_number=0

    def paragraph(value, custom_style=style):
        return Paragraph(escape(str(value or '')).replace('\n','<br/>'), custom_style)

    def draw_paragraph(p,x,top,available_width):
        _,h=p.wrap(available_width,1000000)
        p.drawOn(c,x,top-h)
        return h

    def page_header():
        nonlocal page_number
        page_number+=1
        top=height-margin
        logo_cfg=template.get('logo',{})
        logo=_resolve_asset_path(logo_cfg.get('path'),'logo.png') if layout['show_logo'] else None
        logo_space=64 if logo else 0
        header_x=margin+logo_space; header_width=width-2*margin-logo_space
        top-=draw_paragraph(paragraph(hospital.get('name','').upper(),header_style),header_x,top,header_width)
        details=[hospital.get('address',''), 'Email add: '+hospital.get('email',''), 'Tele: '+hospital.get('tel',''), 'Mobile Nos: '+hospital.get('mobile','')]
        if layout['show_motto'] and hospital.get('motto'):details.append(hospital['motto'])
        top-=draw_paragraph(paragraph('\n'.join(details),detail_style),header_x,top-3,header_width)+3
        if logo:
            c.drawImage(_asset_reader(logo,template.get('transparent_images',True)),margin,height-margin-57,width=56,height=56,preserveAspectRatio=True,mask='auto')
        top=min(top,height-margin-60)-8
        c.setStrokeColor(accent);c.setLineWidth(1);c.line(margin,top,width-margin,top)
        top-=25
        c.setFillColor(colors.black)
        title=layout['title'] + (' - CONTINUED' if page_number>1 else '')
        title_size=min(16,16*(width-2*margin)/max(1,c.stringWidth(title,'Helvetica-Bold',16)))
        c.setFont('Helvetica-Bold',title_size);c.drawCentredString(width/2,top,title)
        top-=22
        name=' '.join(filter(None,[patient.get('first_name',''),patient.get('middle_name',''),patient.get('last_name','')]))
        left_width=(width-2*margin)*.66;right_x=margin+left_width+12;right_width=width-margin-right_x
        for left,right in [('NAME: '+name, 'HOSPITAL NO.: '+draft.get('hospital_no','')),('ADDRESS: '+patient.get('address',''),'AGE: '+str(patient.get('age','') if patient.get('age') is not None else ''))]:
            used=max(draw_paragraph(paragraph(left),margin,top,left_width-8),draw_paragraph(paragraph(right),right_x,top,right_width))
            c.setStrokeColor(colors.HexColor("#555555"));c.setLineWidth(.5)
            c.line(margin,top-used-3,margin+left_width-8,top-used-3)
            c.line(right_x,top-used-3,width-margin,top-used-3)
            top-=used+9
        c.setFont('Helvetica',8);c.setFillColor(colors.HexColor('#526479'))
        c.drawRightString(width-margin,18,f'Page {page_number}')
        c.setFillColor(colors.black);c.setStrokeColor(colors.black);c.setLineWidth(.7)
        c.rect(margin,top-25,width-2*margin,25)
        c.setFont('Helvetica-Bold',10);c.drawString(margin+9,top-17,'DATE: '+draft.get('date',''))
        return top-25

    physician=draft.get('physician',{})
    doctor=physician.get('name','')
    footer_height=max(78,layout['signature_height']+33) if doctor else 0
    y=page_header();bottom=margin+footer_height
    initial_space=y-bottom
    if initial_space < 176:
        raise ValueError("The header or patient details are too long for this paper. Choose larger paper or shorten those fields.")
    weights=[layout[key] for key in ('s_weight','o_weight','a_weight','p_weight')]
    min_heights=[initial_space*weight/sum(weights) for weight in weights]
    if min(min_heights)<44:
        min_heights=[44+(initial_space-176)*weight/sum(weights) for weight in weights]
    text_x=margin+49;text_width=width-margin-text_x-10
    for index,key in enumerate(('S','O','A','P')):
        pending=[paragraph(draft['soap'].get(key,''))];continued=False
        while pending:
            p=pending.pop(0);_,needed=p.wrap(text_width,1000000)
            minimum=min_heights[index] if not continued else 44
            desired=max(minimum,needed+20)
            available=y-bottom
            if available<44:
                c.showPage();y=page_header();available=y-bottom
            if desired>available+0.01 and needed+20<=available:
                # Keep normal minimum row heights when there is room on a fresh page.
                if minimum>available and y<initial_space+bottom-1:
                    c.showPage();y=page_header();available=y-bottom
            if needed+20>available:
                parts=p.split(text_width,max(1,available-20))
                if not parts:
                    c.showPage();y=page_header()
                    if y-bottom<=available+1:raise ValueError('Paper is too small for this header. Reduce the header text or choose larger paper.')
                    pending.insert(0,p);continue
                p=parts[0];pending=parts[1:]+pending
                _,needed=p.wrap(text_width,available-20)
                row_height=available
            else:
                row_height=min(available,max(minimum,needed+20))
            c.rect(margin,y-row_height,width-2*margin,row_height)
            c.setFont('Helvetica-Bold',24);c.drawString(margin+9,y-32,key)
            if continued:
                c.setFont('Helvetica',6);c.drawString(margin+5,y-42,'continued')
            p.drawOn(c,text_x,y-10-needed)
            y-=row_height
            if pending:
                continued=True;c.showPage();y=page_header()
    if doctor:
        center={'Left':margin+105,'Center':width/2,'Right':width-margin-105}[layout['doctor_position']]
        signature=physician.get('signature_path','')
        if draft.get('include_signature'):
            if not signature:
                raise ValueError('No signature is assigned to this doctor.')
            sx,sy,sw,sh=signature_box(layout,width,height)
            c.drawImage(_asset_reader(signature,template.get('transparent_images',True)),sx,height-sy-sh,width=sw,height=sh,preserveAspectRatio=True,mask='auto')
        doctor_style=ParagraphStyle('doctor',parent=style,alignment=1,fontName='Helvetica-Bold')
        doctor_text=paragraph(doctor,doctor_style)
        _,doctor_height=doctor_text.wrap(210,10000)
        if doctor_height>35:raise ValueError('Doctor name is too long for the signature area.')
        doctor_text.drawOn(c,center-105,margin+20-doctor_height)
        c.setFont('Helvetica',8);c.drawCentredString(center,margin+3,'Attending physician')
    c.save()
    return output.getvalue()
