"""Start a disposable hosted preview; bootstrap its owner before opening a port."""
import os
import sys


class ConfigurationError(Exception):
    pass


def prepare():
    # Keep public account creation disabled even when a gateway connects locally.
    os.environ['FESTIVAL_ALLOW_SETUP'] = '0'
    os.environ['FESTIVAL_TEST_DEPLOYMENT'] = '1'
    os.environ.setdefault('FESTIVAL_DATA', '/tmp/festival-demo')
    os.environ.setdefault('FESTIVAL_SECURE_COOKIE', '1')
    os.environ.setdefault('HOST', '0.0.0.0')
    import server

    email = os.environ.pop('FESTIVAL_ADMIN_EMAIL', '').strip().lower()
    pw = os.environ.pop('FESTIVAL_ADMIN_PASSWORD', '').strip()
    server.initialize()
    with server.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        # Existing users, passwords and event data always survive a process restart
        # when the underlying filesystem survives. Never reset them from env vars.
        if db.execute('SELECT 1 FROM users').fetchone():
            return server
        if not email or len(email) > 200 or '@' not in email:
            raise ConfigurationError('FESTIVAL_ADMIN_EMAIL에 관리자 로그인 이메일을 입력하세요.')
        if not 12 <= len(pw) <= 200:
            raise ConfigurationError('FESTIVAL_ADMIN_PASSWORD는 12~200자로 설정하세요.')
        user = server.uid()
        db.execute('INSERT INTO users VALUES(?,?,?,?)',
                   (user, email, '테스트 운영자', server.password(pw)))
        db.execute('INSERT INTO access VALUES(?,?,?)', (user, '*', 'owner'))
    return server


def main():
    try:
        app = prepare()
    except ConfigurationError as error:
        print(str(error), file=sys.stderr, flush=True)
        return 1
    print('Disposable test deployment: data may reset; use fictional information only.', flush=True)
    app.main()
    return 0


if __name__ == '__main__':
    sys.exit(main())
