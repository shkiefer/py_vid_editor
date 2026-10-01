# flask
from flask import Flask, send_from_directory

# dash
import dash
from dash.dependencies import Input, Output, State
from dash import dcc, html
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_uploader as du

# numerical & data processing
import numpy as np

# path, os and filenames & types
from pathlib import Path
import uuid
import io
from base64 import b64encode
from PIL import Image

# media & cv
import moviepy.editor as mpy


APP_ID = 'dss_video'

layout = dbc.Container([
    html.H1('DSS Video Editor'),
    dcc.Store(id=f'{APP_ID}_large_upload_fn_store'),
    du.Upload(id=f'{APP_ID}_large_upload', max_file_size=30720),
    dbc.Row([
        dbc.Col([
            html.Div([
                dbc.Label('Subclip Start (s)'),
                dbc.Input(id=f'{APP_ID}_t_start_input', type='number')
            ]),
            html.Div([
                dbc.Label('Subclip End(s)'),
                dbc.Input(id=f'{APP_ID}_t_end_input', type='number')
            ]),
        ]),
        dbc.Col([
            html.Div([
                dbc.Label('Final Video Width (px)'),
                dbc.Input(id=f'{APP_ID}_vid_w_input', type='number', debounce=True),
            ]),
            html.Div([
                dbc.Label('Final Video Duration (s)'),
                dbc.Input(id=f'{APP_ID}_vid_duration_input', type='number'),
                dbc.FormText('Changes playback speed, eg timelapse or slow-motion')
            ]),
        ]),
        dbc.Col([
            html.Div([
                dbc.Label('Output File Format'),
                dbc.Select(
                    id=f'{APP_ID}_vid_format_select',
                    options=[
                        {'label': 'mpeg', 'value': 'mp4'},
                        {'label': 'wmv', 'value': 'wmv'}
                    ],
                    value='mp4'
                ),
            ]),
        ]),
    ]),
    dbc.Button('Additional Options', id=f'{APP_ID}_options_collapse_button'),
    dbc.Collapse(
        id=f'{APP_ID}_options_collapse',
        children=[
            dbc.Row([
                dbc.Col([
                    html.Div([
                        dbc.Label('Original Video Width (px)'),
                        dbc.Input(id=f'{APP_ID}_vid_ow_input', type='number', debounce=True),
                        dbc.FormText('Used to force / change aspect ratio')
                    ]),
                    html.Div([
                        dbc.Label('Original Video Height (px)'),
                        dbc.Input(id=f'{APP_ID}_vid_oh_input', type='number', debounce=True),
                        dbc.FormText('Used to force / change aspect ratio')
                    ]),
                    html.Div([
                        dbc.Label('Rotate Video'),
                        dbc.Input(id=f'{APP_ID}_vid_rot_input', type='number', debounce=True, value=0.),
                        dbc.FormText('Angle in degrees')
                    ]),
                ]),
                dbc.Col([
                    html.Div([
                        dbc.Label('Crop Top (px)'),
                        dbc.Input(id=f'{APP_ID}_crop_top_input', type='number', value=0)
                    ]),
                    html.Div([
                        dbc.Label('Crop Bottom (px)'),
                        dbc.Input(id=f'{APP_ID}_crop_bot_input', type='number', value=0)
                    ]),
                    html.Div([
                        dbc.Label('Crop Left (px)'),
                        dbc.Input(id=f'{APP_ID}_crop_left_input', type='number', value=0),
                    ]),
                    html.Div([
                        dbc.Label('Crop Right (px)'),
                        dbc.Input(id=f'{APP_ID}_crop_right_input', type='number', value=0)
                    ])
                ]),
                dbc.Col([
                    html.Div([
                        dbc.Label('Logo Image'),
                        dbc.Select(
                            id=f'{APP_ID}_logo_select',
                            options=[
                                {'label': 'None', 'value': 'None'},
                                {'label': 'Redwire Horizontal White', 'value': 'Redwire_Horizontal_White-Red_LOGO.png'},
                                {'label': 'Redwire Horizontal Black', 'value': 'RedWire-Logos_Redwire_Horizontal_Black-Red.png'},
                                {'label': 'Redwire Stacked White', 'value': 'Redwire_Stacked_White-Red_LOGO.png'},
                                {'label': 'Redwire Stacked Black', 'value': 'Redwire_Stacked_Black-Red_LOGO.png'},
                            ],
                            value='Redwire_Horizontal_White-Red_LOGO.png'
                        ),
                    ]),
                    html.Div([
                        dbc.Label('Logo Width (% of final width)'),
                        dbc.Input(id=f'{APP_ID}_logo_w_input', type='number', value=25, min=0, max=100, step=1),
                    ]),
                    html.Div([
                        dbc.Label('Logo Background Opacity'),
                        dbc.Input(id=f'{APP_ID}_logo_opac_input', type='number', value=0.5, min=0., max=1., step=0.01),
                        dbc.FormText('(0: transparent, 1: black)')
                    ]),
                    html.Div([
                        dbc.Label('Border / Margin (px)'),
                        dbc.Input(id=f'{APP_ID}_margin_input', type='number', min=0, max=20, value=5, step=1),
                    ]),
                ]),
                dbc.Col([
                    html.Div([
                        dbc.Label('Logo Location'),
                        dbc.Select(
                            id=f'{APP_ID}_logo_loc_select',
                            options=[
                                {'label': 'Top Left', 'value': 'Top Left'},
                                {'label': 'Top Right', 'value': 'Top Right'},
                                {'label': 'Bottom Right', 'value': 'Bottom Right'},
                                {'label': 'Bottom Left', 'value': 'Bottom Left'},
                            ],
                            value='Top Left'
                        ),
                    ]),
                    html.Div([
                        dbc.Label('Output FPS'),
                        dbc.Input(id=f'{APP_ID}_fps_input', type='number', value=20, min=5, max=60, step=.01),
                    ]),
                    html.Div([
                        dbc.Label('Output Quality'),
                        dbc.Select(
                            id=f'{APP_ID}_vid_quality_select',
                            options=[
                                {'label': i, 'value': str(i)} for i in range(1, 32)
                            ],
                            value='5'
                        ),
                        dbc.FormText('1-31, 1=high quality')
                    ])
                ])

            ])
        ]
    ),
    html.Div([
        dbc.Label('Text Overlay'),
        dbc.Input(id=f'{APP_ID}_text_input', debounce=True, type='text', value='\\nProprietary – Do Not Distribute'),
        dbc.FormText('insert "\\n" for line breaks')
    ]),
    dbc.Row([
        dbc.Col(
            html.Div([
                dbc.Label('Text Size'),
                dbc.Input(id=f'{APP_ID}_text_size_input', type='number', debounce=True, value=30),
            ]),
            width=2
        )
    ]),
    dbc.ButtonGroup([
        dbc.Button('Process Video', id=f'{APP_ID}_process_video_button', color='primary', disabled=True),
        dcc.Loading(
            html.A(
                dbc.Button('Download Video', id=f'{APP_ID}_download_button', color='primary', disabled=True),
                id=f'{APP_ID}_download_link',
                href=''
            )
        )
    ]),
    dcc.Loading(
        html.Div(
            id=f'{APP_ID}_image_div',
            className='mb-4'
        )
    ),
])


def add_dash(app):

    @du.callback(
        output=Output(f'{APP_ID}_large_upload_fn_store', 'data'),
        id=f'{APP_ID}_large_upload',
    )
    def get_a_list(filenames):
        return {i: filenames[i] for i in range(len(filenames))}


    @app.callback(
        [
            Output(f'{APP_ID}_process_video_button', 'disabled'),
            Output(f'{APP_ID}_t_start_input', 'value'),
            Output(f'{APP_ID}_t_end_input', 'value'),
            Output(f'{APP_ID}_vid_w_input', 'value'),
            Output(f'{APP_ID}_vid_ow_input', 'value'),
            Output(f'{APP_ID}_vid_oh_input', 'value'),
            Output(f'{APP_ID}_fps_input', 'value')
        ],
        [
            Input(f'{APP_ID}_large_upload_fn_store', 'data'),
        ],
    )
    def upload_video(dic_of_names):
        if dic_of_names is None:
            return True, 0., None, None, None, None, None
        fn = dic_of_names[list(dic_of_names)[0]]
        clip_1 = mpy.VideoFileClip(str(fn))

        return False, 0., clip_1.duration, clip_1.size[0], clip_1.size[0], clip_1.size[1], clip_1.fps

    @app.callback(
        Output(f'{APP_ID}_options_collapse', "is_open"),
        [Input(f'{APP_ID}_options_collapse_button', "n_clicks")],
        [State(f'{APP_ID}_options_collapse', "is_open")],
    )
    def toggle_vid_options_collapse(n, is_open):
        if n:
            return not is_open
        return is_open

    @app.callback(
        Output(f'{APP_ID}_image_div', 'children'),
        [
            Input(f'{APP_ID}_vid_w_input', 'value'),
            Input(f'{APP_ID}_vid_ow_input', 'value'),
            Input(f'{APP_ID}_vid_oh_input', 'value'),
            Input(f'{APP_ID}_large_upload_fn_store', 'data'),
            Input(f'{APP_ID}_text_input', 'value'),
            Input(f'{APP_ID}_t_start_input', 'value'),
            Input(f'{APP_ID}_t_end_input', 'value'),
            Input(f'{APP_ID}_crop_bot_input', 'value'),
            Input(f'{APP_ID}_crop_top_input', 'value'),
            Input(f'{APP_ID}_crop_left_input', 'value'),
            Input(f'{APP_ID}_crop_right_input', 'value'),
            Input(f'{APP_ID}_logo_w_input', 'value'),
            Input(f'{APP_ID}_text_size_input', 'value'),
            Input(f'{APP_ID}_logo_opac_input', 'value'),
            Input(f'{APP_ID}_margin_input', 'value'),
            Input(f'{APP_ID}_vid_rot_input', 'value'),
            Input(f'{APP_ID}_logo_select', 'value'),
            Input(f'{APP_ID}_logo_loc_select', 'value')
        ],
    )
    def frame_out(video_width, video_orig_width, video_orig_height, dic_of_names, text, clip_start, clip_end, crop_bot, crop_top, crop_left, crop_right, img_wr, text_size, img_op, margin, rot, logo, logo_loc):
        if any([v is None for v in [video_width, dic_of_names, crop_bot, crop_top, crop_left, crop_right, img_wr, img_op, margin, rot, logo]]):
            raise PreventUpdate

        clip_1 = make_clip(
            dic_of_names[list(dic_of_names)[0]],
            logo,
            video_orig_width, video_orig_height, video_width,
            clip_start, clip_end,
            crop_top, crop_bot, crop_left, crop_right,
            text, text_size,
            margin,
            img_wr, img_op,
            rot=rot,
            logo_loc=logo_loc
        )
        # for image export in memory using PIL (for base64 convert), need to apply mask manually
        w = clip_1.size[0]
        if w > 1000: w == 1000
        f = clip_1.fx(mpy.vfx.resize, width=w).get_frame(t=0)
        im = Image.fromarray(f)
        rawBytes = io.BytesIO()
        im.save(rawBytes, "PNG")
        rawBytes.seek(0)

        return html.Img(src=f"data:image/PNG;base64, {b64encode(rawBytes.read()).decode('utf-8')}")



    @app.callback(
        [
            Output(f'{APP_ID}_download_link', 'href'),
            Output(f'{APP_ID}_download_link', 'download'),
            Output(f'{APP_ID}_download_button', 'disabled'),
         ],
        [
            Input(f'{APP_ID}_process_video_button', 'n_clicks'),
        ],
        [
            State(f'{APP_ID}_vid_w_input', 'value'),
            State(f'{APP_ID}_vid_ow_input', 'value'),
            State(f'{APP_ID}_vid_oh_input', 'value'),
            State(f'{APP_ID}_large_upload_fn_store', 'data'),
            State(f'{APP_ID}_text_input', 'value'),
            State(f'{APP_ID}_t_start_input', 'value'),
            State(f'{APP_ID}_t_end_input', 'value'),
            State(f'{APP_ID}_crop_bot_input', 'value'),
            State(f'{APP_ID}_crop_top_input', 'value'),
            State(f'{APP_ID}_crop_left_input', 'value'),
            State(f'{APP_ID}_crop_right_input', 'value'),
            State(f'{APP_ID}_logo_w_input', 'value'),
            State(f'{APP_ID}_text_size_input', 'value'),
            State(f'{APP_ID}_logo_opac_input', 'value'),
            State(f'{APP_ID}_margin_input', 'value'),
            State(f'{APP_ID}_vid_duration_input', 'value'),
            State(f'{APP_ID}_vid_format_select', 'value'),
            State(f'{APP_ID}_fps_input', 'value'),
            State(f'{APP_ID}_vid_quality_select', 'value'),
            State(f'{APP_ID}_vid_rot_input', 'value'),
            State(f'{APP_ID}_logo_select', 'value'),
            State(f'{APP_ID}_logo_loc_select', 'value')
        ]
    )
    def process_pre_video(n_clicks, video_width, video_orig_width, video_orig_height, dic_of_names, text, clip_start, clip_end, crop_bot, crop_top, crop_left, crop_right, img_wr, text_size, img_op, margin, duration, vid_fmt, vid_fps, vid_qual, rot, logo, logo_loc):
        if n_clicks is None:
            raise PreventUpdate

        if dic_of_names is None:
            return None

        clip_1 = make_clip(
            dic_of_names[list(dic_of_names)[0]],
            logo,
            video_orig_width, video_orig_height, video_width,
            clip_start, clip_end,
            crop_top, crop_bot, crop_left, crop_right,
            text, text_size,
            margin, img_wr, img_op,
            rot=rot,
            duration=duration,
            logo_loc=logo_loc
        )

        ffname = Path("downloads") / f'{str(uuid.uuid4())}.{vid_fmt}'
        fn = str(Path(dic_of_names[list(dic_of_names)[0]]).stem) + f'_{video_width}.{vid_fmt}'
        Path.mkdir(ffname.parent, parents=True, exist_ok=True)
        ffname = str(ffname)

        # write full deal
        if vid_fmt == 'mp4':
            clip_1.write_videofile(
                ffname,
                audio=False,
                fps=vid_fps,
                ffmpeg_params=['-qscale:v', f'{vid_qual}']
            )
        if vid_fmt == 'wmv':
            clip_1.write_videofile(
                ffname,
                audio=False,
                codec='msmpeg4',
                fps=vid_fps,
                ffmpeg_params=['-qscale:v', f'{vid_qual}']
            )

        return f'/{ffname}', fn, False

    return app


def make_clip(fn_v, fn_i, video_orig_width, video_orig_height, video_width, clip_start, clip_end, crop_top, crop_bot, crop_left, crop_right, text, text_size, margin, img_wr, img_op, rot=0., duration=None, logo_loc='Top Left'):
    clip = mpy.VideoFileClip(fn_v)
    clip = clip.fx(
        mpy.vfx.resize,
        (int(np.ceil(video_orig_width) // 2 * 2), int(np.ceil(video_orig_height) // 2 * 2))
    )
    clip = clip.subclip(
        t_start=clip_start,
        t_end=clip_end
    )
    if rot != 0:
        clip = clip.fx(
            mpy.vfx.rotate,
            rot
        )
    clip = clip.fx(
        mpy.vfx.crop,
        y1=int(crop_top),
        y2=clip.size[1] - int(crop_bot),
        x1=int(crop_left),
        x2=clip.size[0] - int(crop_right)
    )
    clip = clip.fx(
        mpy.vfx.resize,
        width=int(np.ceil(video_width) // 2 * 2),
        height=int(np.ceil(video_width / video_orig_width * video_orig_height) // 2 * 2),
    )

    clips = [clip]
    if text is not None:
        text = '\n'.join(text.split('\\n'))
        text_clip = mpy.TextClip(
            text,
            color='white',
            font='Calibri-bold',
            fontsize=text_size,
            align='West').set_duration(clip.duration).margin(
            bottom=margin + 5,
            left=margin + 5, top=5, right=5,
            opacity=0
        )
        text_clip = text_clip.on_color(size=text_clip.size, color=(0, 0, 0), col_opacity=0.5)
        clips.append(text_clip.set_position(("left", "bottom")))
    if fn_i != 'None':
        loc_dic = {'Top Left':("left", "top"), 'Top Right': ("right", "top"), 'Bottom Right': ("right", "bottom"), 'Bottom Left': ("left", "bottom")}
        loc = loc_dic[logo_loc]

        p_i = str(Path(app.server.static_folder) / fn_i)
        img_clip = mpy.ImageClip(p_i).set_duration(clip.duration)
        img_clip = img_clip.fx(
            mpy.vfx.resize,
            width=int(np.ceil(clip.w * img_wr/100) // 2 * 2)
        )
        img_clip = img_clip.margin(
            top=int(margin) + 5,
            left=int(margin) + 5,
            bottom=5,
            right=5,
            opacity=0)
        img_clip = img_clip.on_color(
            color=(0, 0, 0),
            col_opacity=float(img_op)
        )
        clips.append(img_clip.set_position(loc))
    clip = mpy.CompositeVideoClip(clips)
    if duration is not None:
        clip = clip.fx(mpy.vfx.accel_decel, new_duration=duration, abruptness=0.0)
    return clip

if __name__ == '__main__':

    external_stylesheets = [
        dbc.themes.BOOTSTRAP,
    ]

    server = Flask(__name__, static_folder=str(Path(__file__).parent.parent / "static/"))
    app = dash.Dash(__name__, server=server, external_stylesheets=external_stylesheets)
    app.config['suppress_callback_exceptions'] = True

    @app.server.route('/downloads/<path:path>')
    def serve_static(path):
        return send_from_directory(
            Path("downloads"), path, as_attachment=True
        )

    du.configure_upload(app, Path.cwd().parent / Path("temp"))

    app.layout = layout
    app = add_dash(app)
    app.run_server(debug=False)

else:
    from dss_analysis_app import app
    # du.configure_upload(app, Path.cwd() / Path("temp"))
    app = add_dash(app)