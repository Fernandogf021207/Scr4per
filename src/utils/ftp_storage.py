r"""
FTP Storage Client for managing file uploads/downloads to remote FTP server.

Organizes files by platform and scraped username:
    ftp/upload/RS/{platform}/{username}/{category}/{filename}

Example structure:
    ftp/upload/RS/red_x/Yerrix3/images/Yerrix3.jpg
    ftp/upload/RS/red_instagram/usuario123/graphs/red_instagram__usuario123.json
"""
import os
import io
import re
import time
import logging
from ftplib import FTP, error_perm
from typing import Optional, List
from functools import wraps

logger = logging.getLogger(__name__)

# Singleton instance
_ftp_client_instance: Optional['FTPClient'] = None


def retry_on_ftp_error(max_attempts=3, backoff=1.0):
    """
    Decorator to retry FTP operations with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        backoff: Initial backoff time in seconds (doubles each retry)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
                        raise
                    wait_time = backoff * (2 ** attempt)
                    logger.warning(f"{func.__name__} failed (attempt {attempt + 1}/{max_attempts}), retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
            return None
        return wrapper
    return decorator


class FTPClient:
    """
    FTP client for file storage operations.
    
    Configuration via environment variables:
        FTP_HOST: FTP server URL (e.g., ftp://192.168.100.200)
        FTP_PORT: FTP port (default: 21)
        FTP_USER_RO: FTP username
        FTP_PASS_RO: FTP password
        FTP_BASE_PATH: Base directory on FTP server (e.g., ftp/upload/RS)
        FTP_TIMEOUT: Connection timeout in seconds (default: 30)
        FTP_ENCODING: File encoding (default: utf-8)
    """
    
    def __init__(self):
        """Initialize FTP client with credentials from environment variables."""
        # Read configuration
        ftp_host_raw = os.getenv('FTP_HOST', 'ftp://192.168.100.200')
        # Strip ftp:// protocol if present
        self.host = ftp_host_raw.replace('ftp://', '').replace('ftps://', '')
        self.port = int(os.getenv('FTP_PORT', '21'))
        self.username = os.getenv('FTP_USER_RO', 'ftpuser')
        self.password = os.getenv('FTP_PASS_RO', '')
        # Base path relative to working directory (ftp/upload)
        # Since we cwd to ftp/upload on connect, this is just 'rs'
        self.base_path = os.getenv('FTP_BASE_PATH', 'rs')
        self.timeout = int(os.getenv('FTP_TIMEOUT', '30'))
        self.encoding = os.getenv('FTP_ENCODING', 'utf-8')
        
        self.connection: Optional[FTP] = None
        # Cache de directorios ya creados para evitar intentos repetidos
        self._created_dirs: set = set()
        
        logger.info(f"FTPClient initialized: {self.host}:{self.port}, base_path={self.base_path}")
    
    def _connect(self) -> FTP:
        """Establish FTP connection."""
        if self.connection:
            try:
                # Test if connection is still alive
                self.connection.voidcmd("NOOP")
                return self.connection
            except Exception:
                # Connection lost, reconnect
                self.connection = None
        
        try:
            logger.info(f"Connecting to FTP server {self.host}:{self.port}...")
            ftp = FTP(timeout=self.timeout)
            ftp.connect(self.host, self.port)
            ftp.login(self.username, self.password)
            ftp.encoding = self.encoding
            
            # Navigate to working directory (ftp/upload)
            # This ensures all paths are relative to /home/ftpuser/ftp/upload
            try:
                ftp.cwd('ftp/upload')
                logger.debug(f"Changed to working directory: {ftp.pwd()}")
            except error_perm as e:
                logger.warning(f"Could not change to ftp/upload: {e}")
            
            self.connection = ftp
            logger.info("FTP connection established successfully")
            return ftp
        except Exception as e:
            logger.error(f"Failed to connect to FTP server: {e}")
            raise ConnectionError(f"FTP connection failed: {e}")
    
    def _disconnect(self):
        """Close FTP connection."""
        if self.connection:
            try:
                self.connection.quit()
            except Exception:
                pass
            finally:
                self.connection = None
    
    def _sanitize_path(self, path_part: str) -> str:
        """
        Sanitize path component to prevent path traversal attacks.
        
        Args:
            path_part: Path component (platform, username, filename)
        
        Returns:
            Sanitized path component
        
        Raises:
            ValueError: If path contains dangerous characters
        """
        if not path_part:
            raise ValueError("Path component cannot be empty")
        
        # Check for path traversal attempts
        if '..' in path_part or '/' in path_part or '\\' in path_part:
            raise ValueError(f"Invalid path component: {path_part}")
        
        # Allow only alphanumeric, dash, underscore, dot
        safe = re.sub(r'[^\w\-\.]', '_', path_part)
        
        # Limit length
        safe = safe[:100]
        
        if not safe:
            raise ValueError(f"Path component resulted in empty string: {path_part}")
        
        return safe
    
    def _build_path(self, platform: str, username: str, category: str, filename: Optional[str] = None) -> str:
        """
        Build FTP path with sanitization.
        
        Args:
            platform: Platform schema (red_x, red_instagram, red_facebook)
            username: Scraped username
            category: File category (images, graphs)
            filename: Optional filename
        
        Returns:
            Sanitized FTP path (forward slashes for FTP)
        """
        # Validate platform
        valid_platforms = ['red_x', 'red_instagram', 'red_facebook']
        if platform not in valid_platforms:
            raise ValueError(f"Invalid platform: {platform}. Must be one of {valid_platforms}")
        
        # Validate category
        valid_categories = ['images', 'graphs']
        if category not in valid_categories:
            raise ValueError(f"Invalid category: {category}. Must be one of {valid_categories}")
        
        # Sanitize components
        safe_platform = self._sanitize_path(platform)
        safe_username = self._sanitize_path(username)
        safe_category = self._sanitize_path(category)
        
        # Build path with forward slashes (FTP standard)
        parts = [self.base_path, safe_platform, safe_username, safe_category]
        
        if filename:
            safe_filename = self._sanitize_path(filename)
            parts.append(safe_filename)
        
        # Use forward slashes for FTP
        path = '/'.join(parts).replace('\\', '/')
        return path
    
    @retry_on_ftp_error(max_attempts=3, backoff=1.0)
    def _ensure_directory(self, path: str):
        """
        Create directory and all parent directories if they don't exist.
        Uses cache to avoid repeated creation attempts for same directory.
        
        Args:
            path: Directory path to create (relative to working dir: ftp/upload)
        """
        # Check cache first - if already created, skip entirely
        if path in self._created_dirs:
            return
        
        ftp = self._connect()
        
        # Build list of all paths (including parents) that need to be created
        parts = [p for p in path.replace('\\', '/').split('/') if p]
        paths_to_create = []
        current = ''
        for part in parts:
            current = f"{current}/{part}" if current else part
            if current not in self._created_dirs:
                paths_to_create.append(current)
        
        # Create directories level by level, only for uncached ones
        for dir_path in paths_to_create:
            try:
                ftp.mkd(dir_path)
                logger.debug(f"Created directory: {dir_path}")
                self._created_dirs.add(dir_path)
            except error_perm as e:
                error_msg = str(e).lower()
                # If directory already exists, silently add to cache
                if 'exists' in error_msg or 'file exists' in error_msg or '550' in str(e):
                    self._created_dirs.add(dir_path)
                else:
                    # Real error, log it
                    logger.warning(f"Could not create directory {dir_path}: {e}")
        
        # Ensure final path is in cache
        self._created_dirs.add(path)
    
    @retry_on_ftp_error(max_attempts=3, backoff=1.0)
    def upload(self, platform: str, username: str, category: str, filename: str, data: bytes) -> str:
        """
        Upload file to FTP server.
        
        Args:
            platform: Platform schema (red_x, red_instagram, red_facebook)
            username: Scraped username
            category: File category (images, graphs)
            filename: Filename
            data: File content as bytes
        
        Returns:
            Relative FTP path: platform/username/category/filename
        
        Raises:
            ValueError: If invalid parameters
            ConnectionError: If FTP operation fails
        """
        file_path = self._build_path(platform, username, category, filename)
        dir_path = self._build_path(platform, username, category)
        
        # Ensure directory exists
        self._ensure_directory(dir_path)
        
        # Upload file
        ftp = self._connect()
        
        # Ensure we're in the correct working directory
        try:
            current = ftp.pwd()
            if not current.endswith('/ftp/upload'):
                ftp.cwd('/ftp/upload')
                logger.debug(f"Reset to working directory: {ftp.pwd()}")
        except:
            pass
        
        bio = io.BytesIO(data)
        
        try:
            ftp.storbinary(f'STOR {file_path}', bio)
            logger.info(f"FTP upload successful: {file_path} ({len(data)} bytes)")
        except Exception as e:
            logger.error(f"FTP upload failed for {file_path}: {e}")
            raise
        
        # Return relative path for DB storage (without base_path)
        relative_path = f"{platform}/{username}/{category}/{filename}"
        return relative_path
    
    @retry_on_ftp_error(max_attempts=3, backoff=1.0)
    def download(self, platform: str, username: str, category: str, filename: str) -> bytes:
        """
        Download file from FTP server.
        
        Args:
            platform: Platform schema
            username: Scraped username
            category: File category
            filename: Filename
        
        Returns:
            File content as bytes
        
        Raises:
            FileNotFoundError: If file doesn't exist
            ConnectionError: If FTP operation fails
        """
        file_path = self._build_path(platform, username, category, filename)
        ftp = self._connect()
        bio = io.BytesIO()
        
        try:
            ftp.retrbinary(f'RETR {file_path}', bio.write)
            logger.info(f"FTP download successful: {file_path} ({bio.tell()} bytes)")
            bio.seek(0)
            return bio.read()
        except error_perm as e:
            if '550' in str(e):  # File not found
                raise FileNotFoundError(f"File not found on FTP: {file_path}")
            raise
    
    @retry_on_ftp_error(max_attempts=3, backoff=1.0)
    def exists(self, platform: str, username: str, category: str, filename: str) -> bool:
        """
        Check if file exists on FTP server.
        
        Args:
            platform: Platform schema
            username: Scraped username
            category: File category
            filename: Filename
        
        Returns:
            True if file exists, False otherwise
        """
        file_path = self._build_path(platform, username, category, filename)
        ftp = self._connect()
        
        try:
            ftp.size(file_path)
            return True
        except error_perm:
            return False
    
    @retry_on_ftp_error(max_attempts=3, backoff=1.0)
    def list_files(self, platform: str, username: str, category: str) -> List[str]:
        """
        List files in directory.
        
        Args:
            platform: Platform schema
            username: Scraped username
            category: File category
        
        Returns:
            List of filenames
        """
        dir_path = self._build_path(platform, username, category)
        ftp = self._connect()
        
        try:
            files = []
            ftp.retrlines(f'NLST {dir_path}', files.append)
            # Extract just filenames
            return [f.split('/')[-1] for f in files]
        except error_perm as e:
            if '550' in str(e):  # Directory not found
                return []
            raise
    
    @retry_on_ftp_error(max_attempts=3, backoff=1.0)
    def delete(self, platform: str, username: str, category: str, filename: str) -> bool:
        """
        Delete file from FTP server.
        
        Args:
            platform: Platform schema
            username: Scraped username
            category: File category
            filename: Filename
        
        Returns:
            True if deleted successfully, False if file didn't exist
        """
        file_path = self._build_path(platform, username, category, filename)
        ftp = self._connect()
        
        try:
            ftp.delete(file_path)
            logger.info(f"FTP delete successful: {file_path}")
            return True
        except error_perm as e:
            if '550' in str(e):  # File not found
                return False
            raise


def get_ftp_client() -> FTPClient:
    """
    Get singleton FTP client instance.
    
    Returns:
        FTPClient instance
    """
    global _ftp_client_instance
    if _ftp_client_instance is None:
        _ftp_client_instance = FTPClient()
    return _ftp_client_instance
