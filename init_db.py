"""Initialize database with tables, admin user, and 48 teams."""
from app import create_app
from models import db, User, Team, SystemSetting
from config import Config
from sqlalchemy import text

app = create_app()

with app.app_context():
    db.create_all()
    print("Tables created.")

    # Migrate: add previous_rank column if missing
    try:
        db.session.execute(text("ALTER TABLE users ADD COLUMN previous_rank INTEGER"))
        db.session.commit()
        print("Column previous_rank added to users table.")
    except Exception:
        print("Column previous_rank already exists (or migration skipped).")

    # Migrate: add country_code column to teams if missing
    try:
        db.session.execute(text("ALTER TABLE teams ADD COLUMN country_code VARCHAR(10)"))
        db.session.commit()
        print("Column country_code added to teams table.")
    except Exception:
        print("Column country_code already exists (or migration skipped).")

    admin = User.query.filter_by(nickname=Config.ADMIN_NICKNAME).first()
    if not admin:
        admin = User(nickname=Config.ADMIN_NICKNAME, is_admin=True)
        admin.set_password(Config.ADMIN_PASSWORD)
        db.session.add(admin)
        db.session.commit()
        print(f"Admin user created: {Config.ADMIN_NICKNAME}")
    else:
        print(f"Admin user already exists: {Config.ADMIN_NICKNAME}")

    # Seed 48 teams (2026 World Cup)
    if Team.query.first() is None:
        zone_map = {
            "A": "C", "B": "D", "C": "C", "D": "B",
            "E": "A", "F": "A", "G": "B", "H": "B",
            "I": "A", "J": "D", "K": "D", "L": "C",
        }
        teams_data = [
            # Group A
            ("墨西哥", "Mexico", "A", "🇲🇽", "mx"),
            ("南非", "South Africa", "A", "🇿🇦", "za"),
            ("韩国", "South Korea", "A", "🇰🇷", "kr"),
            ("捷克", "Czechia", "A", "🇨🇿", "cz"),
            # Group B
            ("加拿大", "Canada", "B", "🇨🇦", "ca"),
            ("波黑", "Bosnia and Herzegovina", "B", "🇧🇦", "ba"),
            ("卡塔尔", "Qatar", "B", "🇶🇦", "qa"),
            ("瑞士", "Switzerland", "B", "🇨🇭", "ch"),
            # Group C
            ("巴西", "Brazil", "C", "🇧🇷", "br"),
            ("摩洛哥", "Morocco", "C", "🇲🇦", "ma"),
            ("海地", "Haiti", "C", "🇭🇹", "ht"),
            ("苏格兰", "Scotland", "C", "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "gb-sct"),
            # Group D
            ("美国", "United States", "D", "🇺🇸", "us"),
            ("巴拉圭", "Paraguay", "D", "🇵🇾", "py"),
            ("澳大利亚", "Australia", "D", "🇦🇺", "au"),
            ("土耳其", "Türkiye", "D", "🇹🇷", "tr"),
            # Group E
            ("德国", "Germany", "E", "🇩🇪", "de"),
            ("库拉索", "Curaçao", "E", "🇨🇼", "cw"),
            ("科特迪瓦", "Côte d'Ivoire", "E", "🇨🇮", "ci"),
            ("厄瓜多尔", "Ecuador", "E", "🇪🇨", "ec"),
            # Group F
            ("荷兰", "Netherlands", "F", "🇳🇱", "nl"),
            ("日本", "Japan", "F", "🇯🇵", "jp"),
            ("瑞典", "Sweden", "F", "🇸🇪", "se"),
            ("突尼斯", "Tunisia", "F", "🇹🇳", "tn"),
            # Group G
            ("比利时", "Belgium", "G", "🇧🇪", "be"),
            ("埃及", "Egypt", "G", "🇪🇬", "eg"),
            ("伊朗", "Iran", "G", "🇮🇷", "ir"),
            ("新西兰", "New Zealand", "G", "🇳🇿", "nz"),
            # Group H
            ("西班牙", "Spain", "H", "🇪🇸", "es"),
            ("佛得角", "Cape Verde", "H", "🇨🇻", "cv"),
            ("沙特", "Saudi Arabia", "H", "🇸🇦", "sa"),
            ("乌拉圭", "Uruguay", "H", "🇺🇾", "uy"),
            # Group I
            ("法国", "France", "I", "🇫🇷", "fr"),
            ("塞内加尔", "Senegal", "I", "🇸🇳", "sn"),
            ("伊拉克", "Iraq", "I", "🇮🇶", "iq"),
            ("挪威", "Norway", "I", "🇳🇴", "no"),
            # Group J
            ("阿根廷", "Argentina", "J", "🇦🇷", "ar"),
            ("阿尔及利亚", "Algeria", "J", "🇩🇿", "dz"),
            ("奥地利", "Austria", "J", "🇦🇹", "at"),
            ("约旦", "Jordan", "J", "🇯🇴", "jo"),
            # Group K
            ("葡萄牙", "Portugal", "K", "🇵🇹", "pt"),
            ("刚果(金)", "DR Congo", "K", "🇨🇩", "cd"),
            ("乌兹别克斯坦", "Uzbekistan", "K", "🇺🇿", "uz"),
            ("哥伦比亚", "Colombia", "K", "🇨🇴", "co"),
            # Group L
            ("英格兰", "England", "L", "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "gb-eng"),
            ("克罗地亚", "Croatia", "L", "🇭🇷", "hr"),
            ("加纳", "Ghana", "L", "🇬🇭", "gh"),
            ("巴拿马", "Panama", "L", "🇵🇦", "pa"),
        ]
        for name, name_en, group_name, flag, country_code in teams_data:
            team = Team(
                name=name,
                name_en=name_en,
                group_name=group_name,
                zone=zone_map.get(group_name),
                flag_emoji=flag,
                country_code=country_code,
            )
            db.session.add(team)
        db.session.commit()
        print(f"Seeded {len(teams_data)} teams.")
    else:
        # Update country_code for existing teams that don't have it
        country_map = {
            "墨西哥": "mx", "南非": "za", "韩国": "kr", "捷克": "cz",
            "加拿大": "ca", "波黑": "ba", "卡塔尔": "qa", "瑞士": "ch",
            "巴西": "br", "摩洛哥": "ma", "海地": "ht", "苏格兰": "gb-sct",
            "美国": "us", "巴拉圭": "py", "澳大利亚": "au", "土耳其": "tr",
            "德国": "de", "库拉索": "cw", "科特迪瓦": "ci", "厄瓜多尔": "ec",
            "荷兰": "nl", "日本": "jp", "瑞典": "se", "突尼斯": "tn",
            "比利时": "be", "埃及": "eg", "伊朗": "ir", "新西兰": "nz",
            "西班牙": "es", "佛得角": "cv", "沙特": "sa", "乌拉圭": "uy",
            "法国": "fr", "塞内加尔": "sn", "伊拉克": "iq", "挪威": "no",
            "阿根廷": "ar", "阿尔及利亚": "dz", "奥地利": "at", "约旦": "jo",
            "葡萄牙": "pt", "刚果(金)": "cd", "乌兹别克斯坦": "uz", "哥伦比亚": "co",
            "英格兰": "gb-eng", "克罗地亚": "hr", "加纳": "gh", "巴拿马": "pa",
        }
        updated = 0
        for t in Team.query.all():
            if not t.country_code and t.name in country_map:
                t.country_code = country_map[t.name]
                updated += 1
        if updated:
            db.session.commit()
            print(f"Updated country_code for {updated} existing teams.")
        else:
            print("Teams already exist, skipping seed (country_codes up to date).")

    print("Database initialized successfully!")
