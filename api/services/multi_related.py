"""Multi-Related Service: Extract subgraph from database.

Implements incremental enrichment by reading already-scraped data
from the database and reconstructing a graph starting from multiple roots.

Does NOT trigger new scraping; only reads existing profiles and relationships.
"""
from __future__ import annotations
from typing import List, Dict, Any, Set, Tuple, Optional
import time
import logging
from collections import deque

from fastapi import HTTPException
from ..db import get_conn
from ..deps import _schema

logger = logging.getLogger(__name__)

ProfileKey = Tuple[str, str]  # (platform, username)


class GraphExtractor:
    """Extracts a subgraph from the database using BFS expansion."""

    def __init__(
        self,
        roots: List[Dict[str, str]],
        depth: int,
        include_inter_root: bool,
        relation_types: Optional[List[str]],
        max_profiles: Optional[int],
    ):
        self.roots = roots
        self.depth = depth
        self.include_inter_root = include_inter_root
        self.relation_types = relation_types
        self.max_profiles = max_profiles

        self.profile_map: Dict[ProfileKey, Dict[str, Any]] = {}
        self.relations: List[Dict[str, Any]] = []
        self.root_keys: Set[ProfileKey] = set()
        self.visited: Set[ProfileKey] = set()
        self.warnings: List[Dict[str, Any]] = []
        self.truncated = False

    def execute(self) -> Dict[str, Any]:
        """Main entry point: extract graph and return formatted payload."""
        start = time.time()

        # Step 1: Resolve root profile IDs from DB
        root_ids = self._resolve_roots()
        if not root_ids:
            return self._build_empty_response(int((time.time() - start) * 1000))

        # Step 2: BFS expansion to desired depth
        self._expand_graph(root_ids)

        # Step 3: Fetch all profile details
        self._fetch_profiles()

        # Step 4: Build final payload
        duration_ms = int((time.time() - start) * 1000)
        return self._build_response(duration_ms)

    def _resolve_roots(self) -> Dict[ProfileKey, int]:
        """Query DB to get profile IDs for all roots. Returns {(platform, username): id}."""
        root_ids: Dict[ProfileKey, int] = {}
        
        with get_conn() as conn:
            with conn.cursor() as cur:
                for root in self.roots:
                    platform = root['platform']
                    username = root['username']
                    schema = _schema(platform)
                    key = (platform, username)
                    
                    try:
                        cur.execute(
                            f"SELECT id FROM {schema}.profiles WHERE platform=%s AND username=%s",
                            (platform, username)
                        )
                        row = cur.fetchone()
                        if row:
                            root_ids[key] = row['id']
                            self.root_keys.add(key)
                        else:
                            self.warnings.append({
                                "code": "ROOT_NOT_FOUND",
                                "message": f"Root {platform}:{username} not found in DB"
                            })
                            logger.warning(f"multi_related.root_not_found platform={platform} username={username}")
                    except Exception as e:
                        logger.exception(f"multi_related.resolve_error platform={platform} username={username}")
                        self.warnings.append({
                            "code": "RESOLVE_ERROR",
                            "message": f"Error resolving {platform}:{username}: {str(e)}"
                        })

        logger.info(f"multi_related.roots_resolved requested={len(self.roots)} found={len(root_ids)}")
        return root_ids

    def _expand_graph(self, root_ids: Dict[ProfileKey, int]):
        """BFS expansion from roots up to specified depth."""
        # Queue: (profile_key, profile_id, current_depth)
        queue: deque[Tuple[ProfileKey, int, int]] = deque()
        
        # Initialize with roots at depth 0
        for key, pid in root_ids.items():
            queue.append((key, pid, 0))
            self.visited.add(key)
            self.profile_map[key] = {
                'platform': key[0],
                'username': key[1],
                'is_root': True,
                'depth_level': 0,
            }

        with get_conn() as conn:
            with conn.cursor() as cur:
                while queue:
                    if self.max_profiles and len(self.profile_map) >= self.max_profiles:
                        self.truncated = True
                        logger.warning(f"multi_related.truncated limit={self.max_profiles}")
                        break

                    current_key, current_id, current_depth = queue.popleft()
                    platform = current_key[0]
                    schema = _schema(platform)

                    # Don't expand beyond max depth
                    if current_depth >= self.depth:
                        continue

                    # Fetch all relationships where this profile is the owner
                    try:
                        rel_filter = ""
                        params = [current_id]
                        if self.relation_types:
                            placeholders = ','.join(['%s'] * len(self.relation_types))
                            rel_filter = f" AND r.rel_type IN ({placeholders})"
                            params.extend(self.relation_types)

                        cur.execute(
                            f"""
                            SELECT p.id, p.platform, p.username, r.rel_type, r.created_at
                            FROM {schema}.relationships r
                            JOIN {schema}.profiles p ON p.id = r.related_profile_id
                            WHERE r.owner_profile_id = %s{rel_filter}
                            """,
                            params
                        )
                        
                        for row in cur.fetchall() or []:
                            related_key = (row['platform'], row['username'])
                            related_id = row['id']
                            
                            # Skip if already visited
                            if related_key in self.visited:
                                # But still record the relation
                                self._add_relation(
                                    platform=platform,
                                    source=current_key[1],
                                    target=related_key[1],
                                    rel_type=row['rel_type'],
                                    created_at=row.get('created_at')
                                )
                                continue

                            # Skip inter-root relations if disabled
                            if not self.include_inter_root:
                                if related_key in self.root_keys and current_key in self.root_keys:
                                    continue

                            # Add to visited and queue
                            self.visited.add(related_key)
                            self.profile_map[related_key] = {
                                'platform': related_key[0],
                                'username': related_key[1],
                                'is_root': related_key in self.root_keys,
                                'depth_level': current_depth + 1,
                            }
                            
                            # Record the relation
                            self._add_relation(
                                platform=platform,
                                source=current_key[1],
                                target=related_key[1],
                                rel_type=row['rel_type'],
                                created_at=row.get('created_at')
                            )

                            # Add to queue for next level expansion
                            if current_depth + 1 < self.depth:
                                queue.append((related_key, related_id, current_depth + 1))

                            # Check truncation limit
                            if self.max_profiles and len(self.profile_map) >= self.max_profiles:
                                self.truncated = True
                                break

                    except Exception as e:
                        logger.exception(f"multi_related.expand_error platform={platform} username={current_key[1]}")
                        self.warnings.append({
                            "code": "EXPANSION_ERROR",
                            "message": f"Error expanding {platform}:{current_key[1]}: {str(e)}"
                        })

        logger.info(f"multi_related.expansion_complete profiles={len(self.profile_map)} relations={len(self.relations)} truncated={self.truncated}")

    def _add_relation(self, platform: str, source: str, target: str, rel_type: str, created_at: Any):
        """Add a relation to the list (deduplicate by tuple)."""
        # Normalize rel_type to English for consistency
        rel_key = (platform, source, target, rel_type)
        # Simple dedup check (not super efficient but works for moderate sizes)
        if not any(
            r['platform'] == platform and 
            r['source'] == source and 
            r['target'] == target and 
            r['type'] == rel_type 
            for r in self.relations
        ):
            self.relations.append({
                'platform': platform,
                'source': source,
                'target': target,
                'type': rel_type,
                'created_at': str(created_at) if created_at else None,
            })

    def _fetch_profiles(self):
        """Fetch full profile details for all profiles in profile_map."""
        if not self.profile_map:
            return

        # Group by platform for efficient queries
        by_platform: Dict[str, List[str]] = {}
        for (platform, username) in self.profile_map.keys():
            by_platform.setdefault(platform, []).append(username)

        with get_conn() as conn:
            with conn.cursor() as cur:
                for platform, usernames in by_platform.items():
                    schema = _schema(platform)
                    placeholders = ','.join(['%s'] * len(usernames))
                    
                    try:
                        cur.execute(
                            f"""
                            SELECT platform, username, full_name, profile_url, photo_url, updated_at
                            FROM {schema}.profiles
                            WHERE platform = %s AND username IN ({placeholders})
                            """,
                            [platform] + usernames
                        )
                        
                        for row in cur.fetchall() or []:
                            key = (row['platform'], row['username'])
                            if key in self.profile_map:
                                self.profile_map[key].update({
                                    'full_name': row.get('full_name'),
                                    'profile_url': row.get('profile_url'),
                                    'photo_url': row.get('photo_url'),
                                    'updated_at': str(row['updated_at']) if row.get('updated_at') else None,
                                })
                    except Exception as e:
                        logger.exception(f"multi_related.fetch_profiles_error platform={platform}")
                        self.warnings.append({
                            "code": "FETCH_ERROR",
                            "message": f"Error fetching profiles for {platform}: {str(e)}"
                        })

    def _build_response(self, duration_ms: int) -> Dict[str, Any]:
        """Build final response payload."""
        root_profile_ids = [f"{p}:{u}" for (p, u) in self.root_keys]
        
        profiles_out = [
            {
                'platform': data['platform'],
                'username': data['username'],
                'full_name': data.get('full_name'),
                'profile_url': data.get('profile_url'),
                'photo_url': data.get('photo_url'),
                'is_root': data.get('is_root', False),
                'depth_level': data.get('depth_level', 0),
                'updated_at': data.get('updated_at'),
            }
            for key, data in self.profile_map.items()
        ]

        return {
            'schema_version': 2,
            'root_profiles': root_profile_ids,
            'profiles': profiles_out,
            'relations': self.relations,
            'meta': {
                'roots_requested': len(self.roots),
                'roots_found': len(self.root_keys),
                'total_profiles': len(self.profile_map),
                'total_relations': len(self.relations),
                'depth_executed': self.depth,
                'query_duration_ms': duration_ms,
                'truncated': self.truncated,
            },
            'warnings': self.warnings,
        }

    def _build_empty_response(self, duration_ms: int) -> Dict[str, Any]:
        """Response when no roots were found."""
        return {
            'schema_version': 2,
            'root_profiles': [],
            'profiles': [],
            'relations': [],
            'meta': {
                'roots_requested': len(self.roots),
                'roots_found': 0,
                'total_profiles': 0,
                'total_relations': 0,
                'depth_executed': self.depth,
                'query_duration_ms': duration_ms,
                'truncated': False,
            },
            'warnings': self.warnings,
        }


async def multi_related_execute(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Main service function for multi-related endpoint.
    
    Args:
        request_data: Dict with keys: roots, depth, include_inter_root_relations, 
                      relation_types, max_profiles
    
    Returns:
        Dict matching MultiRelatedResponse schema
    """
    roots = request_data.get('roots', [])
    depth = request_data.get('depth', 1)
    include_inter_root = request_data.get('include_inter_root_relations', True)
    relation_types = request_data.get('relation_types')
    max_profiles = request_data.get('max_profiles')

    if not roots:
        raise HTTPException(status_code=422, detail={"code": "VALIDATION_ERROR", "message": "No roots provided"})

    # Convert Pydantic models to dicts if needed
    roots_list = [
        {'platform': r.platform, 'username': r.username} if hasattr(r, 'platform') else r
        for r in roots
    ]

    extractor = GraphExtractor(
        roots=roots_list,
        depth=depth,
        include_inter_root=include_inter_root,
        relation_types=relation_types,
        max_profiles=max_profiles,
    )

    try:
        return extractor.execute()
    except Exception as e:
        logger.exception("multi_related.execute_error")
        raise HTTPException(status_code=500, detail={
            "code": "EXTRACTION_ERROR",
            "message": f"Failed to extract graph: {str(e)}"
        })
