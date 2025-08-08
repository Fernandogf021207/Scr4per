from db.insert import get_conn, upsert_profile, add_relationship, add_post, add_comment

if __name__ == "__main__":
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 1) Perfil
            pid = upsert_profile(cur, 'x', 'ibaillanos', full_name='Ibai Llanos', profile_url='https://x.com/ibaillanos')
            print('profile id:', pid)
            # 2) Follower
            rid = add_relationship(cur, 'x', 'ibaillanos', 'some_follower', 'follower')
            print('relationship id:', rid)
            # 3) Post
            post_id = add_post(cur, 'x', 'ibaillanos', 'https://x.com/ibaillanos/status/1234567890')
            print('post id:', post_id)
            # 4) Comment
            cid = add_comment(cur, 'x', 'https://x.com/ibaillanos/status/1234567890', 'comment_user')
            print('comment id:', cid)
