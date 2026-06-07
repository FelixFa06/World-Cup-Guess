"""Initialize database with tables, admin user, and 48 teams."""
from app import create_app
from models import db, User, Team
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
            ("墨西哥", "Mexico", "A", "🇲🇽"),
            ("南非", "South Africa", "A", "🇿🇦"),
            ("韩国", "South Korea", "A", "🇰🇷"),
            ("捷克", "Czechia", "A", "🇨🇿"),
            # Group B
            ("加拿大", "Canada", "B", "🇨🇦"),
            ("波黑", "Bosnia and Herzegovina", "B", "🇧🇦"),
            ("卡塔尔", "Qatar", "B", "🇶🇦"),
            ("瑞士", "Switzerland", "B", "🇨🇭"),
            # Group C
            ("巴西", "Brazil", "C", "🇧🇷"),
            ("摩洛哥", "Morocco", "C", "🇲🇦"),
            ("海地", "Haiti", "C", "🇭🇹"),
            ("苏格兰", "Scotland", "C", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
            # Group D
            ("美国", "United States", "D", "🇺🇸"),
            ("巴拉圭", "Paraguay", "D", "🇵🇾"),
            ("澳大利亚", "Australia", "D", "🇦🇺"),
            ("土耳其", "Türkiye", "D", "🇹🇷"),
            # Group E
            ("德国", "Germany", "E", "🇩🇪"),
            ("库拉索", "Curaçao", "E", "🇨🇼"),
            ("科特迪瓦", "Côte d'Ivoire", "E", "🇨🇮"),
            ("厄瓜多尔", "Ecuador", "E", "🇪🇨"),
            # Group F
            ("荷兰", "Netherlands", "F", "🇳🇱"),
            ("日本", "Japan", "F", "🇯🇵"),
            ("瑞典", "Sweden", "F", "🇸🇪"),
            ("突尼斯", "Tunisia", "F", "🇹🇳"),
            # Group G
            ("比利时", "Belgium", "G", "🇧🇪"),
            ("埃及", "Egypt", "G", "🇪🇬"),
            ("伊朗", "Iran", "G", "🇮🇷"),
            ("新西兰", "New Zealand", "G", "🇳🇿"),
            # Group H
            ("西班牙", "Spain", "H", "🇪🇸"),
            ("佛得角", "Cape Verde", "H", "🇨🇻"),
            ("沙特", "Saudi Arabia", "H", "🇸🇦"),
            ("乌拉圭", "Uruguay", "H", "🇺🇾"),
            # Group I
            ("法国", "France", "I", "🇫🇷"),
            ("塞内加尔", "Senegal", "I", "🇸🇳"),
            ("伊拉克", "Iraq", "I", "🇮🇶"),
            ("挪威", "Norway", "I", "🇳🇴"),
            # Group J
            ("阿根廷", "Argentina", "J", "🇦🇷"),
            ("阿尔及利亚", "Algeria", "J", "🇩🇿"),
            ("奥地利", "Austria", "J", "🇦🇹"),
            ("约旦", "Jordan", "J", "🇯🇴"),
            # Group K
            ("葡萄牙", "Portugal", "K", "🇵🇹"),
            ("刚果(金)", "DR Congo", "K", "🇨🇩"),
            ("乌兹别克斯坦", "Uzbekistan", "K", "🇺🇿"),
            ("哥伦比亚", "Colombia", "K", "🇨🇴"),
            # Group L
            ("英格兰", "England", "L", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
            ("克罗地亚", "Croatia", "L", "🇭🇷"),
            ("加纳", "Ghana", "L", "🇬🇭"),
            ("巴拿马", "Panama", "L", "🇵🇦"),
        ]
        for name, name_en, group_name, flag in teams_data:
            team = Team(
                name=name,
                name_en=name_en,
                group_name=group_name,
                zone=zone_map.get(group_name),
                flag_emoji=flag,
            )
            db.session.add(team)
        db.session.commit()
        print(f"Seeded {len(teams_data)} teams.")
    else:
        print("Teams already exist, skipping seed.")

    print("Database initialized successfully!")
