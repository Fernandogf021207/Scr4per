"""
Utilidades de navegación para Facebook.
Maneja diferentes formatos de URLs (username vs numeric ID).
"""
from typing import Optional
import re


class FacebookNavigation:
    """Construye URLs de Facebook para diferentes tipos de perfil."""
    
    BASE_URL = "https://www.facebook.com"
    
    @staticmethod
    def build_profile_url(identifier: str) -> str:
        """
        Construye URL del perfil principal.
        
        Args:
            identifier: Username (juan.perez) o ID numérico (100012345)
            
        Returns:
            URL del perfil
        """
        if FacebookNavigation._is_numeric_id(identifier):
            return f"{FacebookNavigation.BASE_URL}/profile.php?id={identifier}"
        else:
            return f"{FacebookNavigation.BASE_URL}/{identifier}"
    
    @staticmethod
    def build_friends_url(identifier: str) -> str:
        """
        Construye URL de la lista de amigos.
        
        Args:
            identifier: Username (juan.perez) o ID numérico (100012345)
            
        Returns:
            URL de amigos
        """
        if FacebookNavigation._is_numeric_id(identifier):
            return f"{FacebookNavigation.BASE_URL}/profile.php?id={identifier}&sk=friends"
        else:
            return f"{FacebookNavigation.BASE_URL}/{identifier}/friends"
    
    @staticmethod
    def get_friends_url(profile_id: str) -> str:
        """
        Alias de build_friends_url para compatibilidad.
        Detecta automáticamente si es ID numérico o username.
        
        Args:
            profile_id: ID numérico (100012345) o username (juan.perez)
            
        Returns:
            URL de la lista de amigos
        """
        return FacebookNavigation.build_friends_url(profile_id)
    
    @staticmethod
    def build_photos_url(identifier: str) -> str:
        """
        Construye URL de fotos del perfil.
        
        Args:
            identifier: Username (juan.perez) o ID numérico (100012345)
            
        Returns:
            URL de fotos
        """
        if FacebookNavigation._is_numeric_id(identifier):
            return f"{FacebookNavigation.BASE_URL}/profile.php?id={identifier}&sk=photos"
        else:
            return f"{FacebookNavigation.BASE_URL}/{identifier}/photos"
    
    @staticmethod
    def build_followers_url(identifier: str) -> str:
        """
        Construye URL de seguidores.
        
        Args:
            identifier: Username (juan.perez) o ID numérico (100012345)
            
        Returns:
            URL de seguidores
        """
        if FacebookNavigation._is_numeric_id(identifier):
            return f"{FacebookNavigation.BASE_URL}/profile.php?id={identifier}&sk=followers"
        else:
            return f"{FacebookNavigation.BASE_URL}/{identifier}/followers"
    
    @staticmethod
    def build_following_url(identifier: str) -> str:
        """
        Construye URL de seguidos.
        
        Args:
            identifier: Username (juan.perez) o ID numérico (100012345)
            
        Returns:
            URL de seguidos
        """
        if FacebookNavigation._is_numeric_id(identifier):
            return f"{FacebookNavigation.BASE_URL}/profile.php?id={identifier}&sk=following"
        else:
            return f"{FacebookNavigation.BASE_URL}/{identifier}/following"
    
    @staticmethod
    def extract_identifier_from_url(url: str) -> Optional[str]:
        """
        Extrae el identificador (username o ID) de una URL de Facebook.
        
        Args:
            url: URL de Facebook
            
        Returns:
            Username o ID numérico, o None si no se puede extraer
        """
        # Intenta extraer ID numérico: profile.php?id=123456
        numeric_match = re.search(r'profile\.php\?id=(\d+)', url)
        if numeric_match:
            return numeric_match.group(1)
        
        # Intenta extraer username: facebook.com/username o facebook.com/username/friends
        username_match = re.search(r'facebook\.com/([^/?]+)', url)
        if username_match:
            username = username_match.group(1)
            # Excluye rutas especiales como 'profile.php', 'home', etc.
            if username not in ['profile.php', 'home', 'watch', 'marketplace', 'groups']:
                return username
        
        return None
    
    @staticmethod
    def _is_numeric_id(identifier: str) -> bool:
        """
        Verifica si el identificador es un ID numérico.
        
        Args:
            identifier: Identificador a verificar
            
        Returns:
            True si es numérico, False si es username
        """
        return identifier.isdigit()
    
    @staticmethod
    def is_login_url(url: str) -> bool:
        """
        Verifica si la URL actual es una página de login.
        
        Args:
            url: URL actual
            
        Returns:
            True si es página de login
        """
        login_patterns = [
            'facebook.com/login',
            'facebook.com/checkpoint',
            'facebook.com/login.php',
            'facebook.com/recover',
            'facebook.com/confirmemail.php'
        ]
        return any(pattern in url.lower() for pattern in login_patterns)
    
    @staticmethod
    def is_checkpoint_url(url: str) -> bool:
        """
        Verifica si la URL actual es un checkpoint de seguridad.
        
        Args:
            url: URL actual
            
        Returns:
            True si es checkpoint
        """
        checkpoint_patterns = [
            'facebook.com/checkpoint',
            'facebook.com/x/checkpoint',
            'facebook.com/nt/screen',
            'facebook.com/communitystandards'
        ]
        return any(pattern in url.lower() for pattern in checkpoint_patterns)
