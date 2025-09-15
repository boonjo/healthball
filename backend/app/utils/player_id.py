import hashlib
from unidecode import unidecode

def generate_player_id(name: str, birth_year: str = None, length: int = 8):
    """
    Generate a short numeric hash ID for a player

    :param name:  Player name
    :param birth_year: Birth year of the player to reduce collisions
    :param length: Number of digits for ID generation
    :return:
        str: Short numeric ID as string
    """
    key = name.lower().strip()
    if birth_year:
        key += str(birth_year)

    h = int(hashlib.sha256(key.encode('utf-8')).hexdigest(), 16)
    player_id = str(h % (10**length))
    return player_id

def slugify_name(name: str):
    """
    Convert names to lowercase, replace spaces with _, strip accents

    :param name: Player name
    :return:
        str: Slugified name
    """
    return unidecode(name.lower().replace(' ', '_'))
