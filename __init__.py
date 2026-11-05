__version__ = '1.0.1'
from .anima_character_sheet.node import AnimaCharacterSheetDesigner
from .anima_character_sheet.assemble import AnimaCharacterSheetAssemble
from .anima_character_sheet.tagger_node import AnimaImageTagger

NODE_CLASS_MAPPINGS = {'AnimaCharacterSheetDesigner': AnimaCharacterSheetDesigner,
                       'AnimaCharacterSheetAssemble': AnimaCharacterSheetAssemble,
                       'AnimaImageTagger': AnimaImageTagger}
NODE_DISPLAY_NAME_MAPPINGS = {'AnimaCharacterSheetDesigner': 'Anima Character Sheet Designer',
                              'AnimaCharacterSheetAssemble': 'Anima Character Sheet Assemble',
                              'AnimaImageTagger': 'Anima Image Tagger (WD / PixAI FP16)'}
WEB_DIRECTORY = './web'

try:
    from server import PromptServer
except ImportError:
    PromptServer = None
if PromptServer is not None and getattr(PromptServer, 'instance', None) is not None:
    from .anima_character_sheet.preview import register_preview
    register_preview()
