"""Image validation for Assemble and lazy tagger preprocessing."""
import hashlib
import struct
from .state import fail

def check_image(image,path='image'):
    import torch
    if not isinstance(image,torch.Tensor) or image.ndim!=4 or image.shape[0]!=1 or image.shape[-1] not in (3,4): fail('E_IMAGE_INVALID',path,'Expected one RGB/RGBA image.')
    if not image.is_floating_point() or min(image.shape[1:3])<1 or image.shape[1]*image.shape[2]>64000000: fail('E_IMAGE_SIZE',path)
    if not bool(torch.isfinite(image).all()) or bool((image<0).any()) or bool((image>1).any()): fail('E_NONFINITE_IMAGE',path)

def tensor_rgb(image,mask=None):
    import torch
    import numpy as np
    check_image(image)
    if mask is not None:
        if not isinstance(mask,torch.Tensor) or not mask.is_floating_point() or mask.ndim!=3 or mask.shape[0]!=1: fail('E_MASK_INVALID','mask')
        if not bool(torch.isfinite(mask).all()) or bool((mask<0).any()) or bool((mask>1).any()): fail('E_MASK_INVALID','mask')
        if image.shape[-1]==4: fail('E_MASK_INVALID','mask','Use alpha OR mask.')
        if bool((mask==0).all()) and tuple(mask.shape)==(1,64,64): mask=None
        elif tuple(mask.shape)!=tuple(image.shape[:3]) or bool((mask==1).all()): fail('E_MASK_INVALID','mask')
    rgb=image.detach().to(device='cpu',dtype=torch.float32)
    if rgb.shape[-1]==4:
        alpha=rgb[...,3:4]
        if not bool((alpha>0).any()): fail('E_MASK_INVALID','alpha')
        rgb=rgb[...,:3]*alpha+1-alpha
    elif mask is not None:
        m=mask.detach().to(device='cpu',dtype=torch.float32).unsqueeze(-1)
        rgb=rgb*(1-m)+m
    return np.ascontiguousarray(np.rint(rgb[0].numpy()*255).astype(np.uint8))

def input_path(name):
    import folder_paths
    from pathlib import Path
    if not isinstance(name,str) or not name or '\x00' in name or ':' in name: fail('E_IMAGE_PATH','image_name')
    relative=Path(name.replace('\\','/'))
    root=Path(folder_paths.get_input_directory()).resolve()
    path=(root/relative).resolve()
    if relative.is_absolute() or '..' in relative.parts or not path.is_relative_to(root): fail('E_IMAGE_PATH','image_name')
    if not path.is_file(): fail('E_IMAGE_MISSING','image_name')
    return path

def file_rgb(name):
    import numpy as np
    from PIL import Image, ImageOps
    path=input_path(name)
    with Image.open(path) as image:
        if getattr(image,'n_frames',1)!=1: fail('E_IMAGE_BATCH','image_name')
        if image.width*image.height>64000000: fail('E_IMAGE_SIZE','image_name')
        image=ImageOps.exif_transpose(image).convert('RGBA')
        if image.getchannel('A').getextrema()[1]==0: fail('E_MASK_INVALID','alpha')
        white=Image.new('RGBA',image.size,'white'); white.alpha_composite(image)
        return np.ascontiguousarray(np.asarray(white.convert('RGB')))

def pixel_hash(rgb):
    return hashlib.sha256(b'anima-tagger-image-v1\0'+struct.pack('<II',rgb.shape[1],rgb.shape[0])+rgb.tobytes()).hexdigest()

def preprocess(rgb,model_id):
    import numpy as np
    from PIL import Image
    image=Image.fromarray(rgb)
    if model_id=='pixai_v1_fp16':
        scale=1008/max(image.size)
        size=tuple(max(1,round(n*scale)) for n in image.size)
        image=image.resize(size,Image.Resampling.BICUBIC)
        square=Image.new('RGB',(1008,1008),(0,0,0)); square.paste(image,((1008-size[0])//2,(1008-size[1])//2))
        return np.ascontiguousarray(((np.asarray(square,dtype=np.float32)/255-.5)/.5).transpose(2,0,1)[None])
    if model_id=='wd_eva02_large_v3':
        side=max(image.size); square=Image.new('RGB',(side,side),'white')
        square.paste(image,((side-image.width)//2,(side-image.height)//2))
        return np.ascontiguousarray(np.asarray(square.resize((448,448),Image.Resampling.BICUBIC),dtype=np.float32)[None,...,::-1])
    fail('E_TAGGER_MODEL','model_id')
