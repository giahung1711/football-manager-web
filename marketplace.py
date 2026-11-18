import copy
import math
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models import db, GameSave, PlayerMarketListing, User
from game_engine import normalize_state, player_upgrade_ovr, value, MAX_UPGRADE_LEVEL

player_market_bp = Blueprint("player_market", __name__)


def _get_save(user_id, lock=False):
    query = GameSave.query.filter_by(user_id=user_id)
    if lock:
        query = query.with_for_update()
    return query.first()


def _read_state(save):
    state = normalize_state(copy.deepcopy(save.state or {}))
    state.setdefault("pending_market_money", 0.0)
    return state


def _write_state(save, state):
    save.state = copy.deepcopy(state)
    db.session.add(save)


def _market_removed_names(state):
    names = state.get("market_removed_players", [])
    if not isinstance(names, list):
        names = []
    state["market_removed_players"] = names
    return names


def _mark_market_removed(state, player_name):
    names = _market_removed_names(state)
    key = str(player_name).strip().casefold()

    if key and not any(
        str(name).strip().casefold() == key
        for name in names
    ):
        names.append(str(player_name).strip())


def _unmark_market_removed(state, player_name):
    key = str(player_name).strip().casefold()

    state["market_removed_players"] = [
        name for name in _market_removed_names(state)
        if str(name).strip().casefold() != key
    ]


@player_market_bp.get("/player-market")
@login_required
def player_market():
    save = _get_save(current_user.id)

    if not save:
        return redirect(url_for("choose_club"))

    state = _read_state(save)

    active_listings = (
        PlayerMarketListing.query
        .filter_by(status="active")
        .order_by(
            PlayerMarketListing.created_at.desc(),
            PlayerMarketListing.id.desc()
        )
        .all()
    )

    # Build display-safe values for every listing. Never index a fixed-size
    # OVR bonus array with the raw stored card level: malformed/legacy levels
    # such as +585 must not crash the entire marketplace page.
    for listing in active_listings:
        player_data = listing.player_data if isinstance(listing.player_data, dict) else {}
        try:
            raw_level = int(player_data.get("level", 0) or 0)
        except (TypeError, ValueError, OverflowError):
            raw_level = 0
        listing.display_level = raw_level
        try:
            listing.display_ovr = player_upgrade_ovr(player_data)
        except (TypeError, ValueError, OverflowError):
            try:
                listing.display_ovr = int(player_data.get("rating", 80) or 80)
            except (TypeError, ValueError, OverflowError):
                listing.display_ovr = 80
        listing.display_position = str(player_data.get("position", "—") or "—")
        listing.display_ultimate = bool(player_data.get("ultimate"))

    seller_ids = {item.seller_id for item in active_listings}

    sellers = {
        user.id: user.username
        for user in User.query.filter(User.id.in_(seller_ids)).all()
    } if seller_ids else {}

    own_players = []

    for group in ("bench", "extras"):
        for index, p in enumerate(state.get(group, [])):
            level = int(p.get("level", 0) or 0)
            current_ovr = player_upgrade_ovr(p)
            current_value = value(p)

            if current_ovr <= 89:
                eligible = level >= 5
                requirement = "Thẻ +5 trở lên"
            elif current_ovr <= 95:
                eligible = level >= 3
                requirement = "Thẻ +3 trở lên"
            else:
                eligible = True
                requirement = "Không giới hạn cấp thẻ"

            own_players.append({
                "group": group,
                "index": index,
                "player": p,
                "ovr": current_ovr,
                "value": current_value,
                "minimum": round(current_value * 0.90, 2),
                "maximum": round(current_value * 1.10, 2),
                "eligible": eligible,
                "requirement": requirement,
            })

    return render_template(
        "player_market.html",
        state=state,
        listings=active_listings,
        sellers=sellers,
        own_players=own_players,
    )


@player_market_bp.post("/player-market/list")
@login_required
def player_market_list():
    save = _get_save(current_user.id, lock=True)

    if not save:
        return redirect(url_for("choose_club"))

    try:
        state = _read_state(save)

        group = request.form.get("group", "")
        index = int(request.form.get("index", "-1"))

        if group not in {"bench", "extras"}:
            raise ValueError(
                "Chỉ có thể đăng bán cầu thủ trong mục Dự bị hoặc Cầu thủ khác."
            )

        players = state.get(group, [])

        if index < 0 or index >= len(players):
            raise ValueError("Không tìm thấy cầu thủ được chọn.")

        p = players[index]

        level = int(p.get("level", 0) or 0)
        current_ovr = player_upgrade_ovr(p)
        current_value = value(p)

        if current_value <= 0:
            raise ValueError("Giá trị cầu thủ không hợp lệ.")

        if current_ovr <= 89 and level < 5:
            raise ValueError(
                "Cầu thủ OVR 89 trở xuống phải đạt cấp thẻ +5 trở lên mới được đăng bán."
            )

        if 90 <= current_ovr <= 95 and level < 3:
            raise ValueError(
                "Cầu thủ OVR 90–95 phải đạt cấp thẻ +3 trở lên mới được đăng bán."
            )

        try:
            asking_price = float(
                request.form.get("asking_price", "")
            )
        except (TypeError, ValueError):
            raise ValueError("Vui lòng nhập giá bán hợp lệ.")

        minimum = current_value * 0.90
        maximum = current_value * 1.10

        if asking_price < minimum - 1e-8 or asking_price > maximum + 1e-8:
            raise ValueError(
                f"Giá bán phải nằm trong khoảng "
                f"{minimum:.2f}–{maximum:.2f} M PC (90%–110% giá trị hiện tại)."
            )

        listing = PlayerMarketListing(
            seller_id=current_user.id,
            player_name=p["name"],
            player_data=copy.deepcopy(p),
            player_group=group,
            asking_price=round(asking_price, 2),
            status="active",
        )

        # Đưa cầu thủ ra khỏi đội và đánh dấu đã rời CLB.
        players.pop(index)
        _mark_market_removed(state, p["name"])

        _write_state(save, state)
        db.session.add(listing)
        db.session.commit()

        flash(
            f"Đã đăng bán {p['name']} với giá {asking_price:.2f} M PC."
        )

    except ValueError as exc:
        db.session.rollback()
        flash(str(exc))

    except Exception:
        db.session.rollback()
        flash("Không thể đăng bán lúc này. Dữ liệu chưa được thay đổi.")

    return redirect(url_for("player_market.player_market"))


@player_market_bp.post("/player-market/list-bulk")
@login_required
def player_market_list_bulk():
    save = _get_save(current_user.id, lock=True)
    if not save:
        return redirect(url_for("choose_club"))
    try:
        state = _read_state(save)
        selected = request.form.getlist("selected_player")
        if not selected:
            raise ValueError("Hãy chọn ít nhất một cầu thủ để đăng bán.")

        parsed = []
        seen = set()
        for token in selected:
            group, raw_index = token.split(":", 1)
            index = int(raw_index)
            if group not in {"bench", "extras"} or index < 0 or index >= len(state.get(group, [])):
                raise ValueError("Danh sách cầu thủ được chọn không hợp lệ. Hãy tải lại trang.")
            key = (group, index)
            if key in seen:
                continue
            seen.add(key)
            player_record = state[group][index]
            level = int(player_record.get("level", 0) or 0)
            current_ovr = player_upgrade_ovr(player_record)
            current_value = value(player_record)
            if current_value <= 0:
                raise ValueError(f"Giá trị của {player_record.get('name', 'cầu thủ')} không hợp lệ.")
            if current_ovr <= 89 and level < 5:
                raise ValueError(f"{player_record['name']} cần đạt +5 trở lên mới được đăng bán.")
            if 90 <= current_ovr <= 95 and level < 3:
                raise ValueError(f"{player_record['name']} cần đạt +3 trở lên mới được đăng bán.")
            try:
                asking_price = float(request.form.get(f"price_{group}_{index}", current_value))
            except (TypeError, ValueError):
                raise ValueError(f"Giá bán của {player_record['name']} không hợp lệ.")
            if not math.isfinite(asking_price) or asking_price < current_value * .90 - 1e-8 or asking_price > current_value * 1.10 + 1e-8:
                raise ValueError(f"Giá bán {player_record['name']} phải nằm trong khoảng 90%–110% giá trị hiện tại.")
            parsed.append((group, index, copy.deepcopy(player_record), round(asking_price, 2)))

        # Validate everything first, then remove in descending index order to keep indexes stable.
        for group, index, player_record, asking_price in parsed:
            db.session.add(PlayerMarketListing(
                seller_id=current_user.id, player_name=player_record["name"],
                player_data=player_record, player_group=group,
                asking_price=asking_price, status="active"
            ))
        by_group = {"bench": [], "extras": []}
        for group, index, _, _ in parsed:
            by_group[group].append(index)
        for group, indexes in by_group.items():
            for index in sorted(indexes, reverse=True):
                player_record = state[group].pop(index)
                _mark_market_removed(state, player_record["name"])
        _write_state(save, state)
        db.session.commit()
        flash(f"Đã đăng bán thành công {len(parsed)} cầu thủ.")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc))
    except Exception:
        db.session.rollback()
        flash("Không thể đăng bán hàng loạt. Dữ liệu đội hình và tin đăng được giữ nguyên.")
    return redirect(url_for("player_market.player_market"))


@player_market_bp.post("/player-market/buy/<int:listing_id>")
@login_required
def player_market_buy(listing_id):
    try:
        listing = (
            PlayerMarketListing.query
            .filter_by(id=listing_id)
            .with_for_update()
            .first()
        )

        if not listing or listing.status != "active":
            raise ValueError(
                "Cầu thủ này đã được người khác mua hoặc không còn được rao bán."
            )

        if listing.seller_id == current_user.id:
            raise ValueError("Bạn không thể tự mua cầu thủ do mình đăng bán.")

        # Khóa dữ liệu hai đội bóng theo thứ tự ID.
        user_ids = sorted({listing.seller_id, current_user.id})

        saves = (
            GameSave.query
            .filter(GameSave.user_id.in_(user_ids))
            .order_by(GameSave.user_id.asc())
            .with_for_update()
            .all()
        )

        saves_by_user = {
            item.user_id: item
            for item in saves
        }

        buyer_save = saves_by_user.get(current_user.id)
        seller_save = saves_by_user.get(listing.seller_id)

        if not buyer_save or not seller_save:
            raise ValueError(
                "Không tìm thấy dữ liệu đội bóng của người mua hoặc người bán."
            )

        buyer_state = _read_state(buyer_save)
        seller_state = _read_state(seller_save)

        price = round(float(listing.asking_price), 2)
        player_record = copy.deepcopy(listing.player_data)

        if buyer_state["budget"] + 1e-9 < price:
            raise ValueError("Bạn không đủ ngân sách để mua cầu thủ này.")

        # Chỉ một giao dịch được phép chuyển tin đăng sang sold.
        from sqlalchemy import update

        result = db.session.execute(
            update(PlayerMarketListing)
            .where(
                PlayerMarketListing.id == listing_id,
                PlayerMarketListing.status == "active",
            )
            .values(
                status="sold",
                buyer_id=current_user.id,
                sold_at=datetime.utcnow(),
            )
        )

        if result.rowcount != 1:
            raise ValueError("Cầu thủ này đã được người khác mua.")

        # Trừ tiền người mua.
        buyer_state["budget"] = round(
            float(buyer_state["budget"]) - price,
            2
        )

        # Xóa dấu rời CLB cũ nếu người mua từng bán cầu thủ cùng tên.
        _unmark_market_removed(buyer_state, listing.player_name)

        # Đưa cầu thủ vào Dự bị, giữ nguyên dữ liệu.
        buyer_state.setdefault("bench", []).append(player_record)

        # Tiền người bán được đưa vào mục chờ nhận.
        seller_state["pending_market_money"] = round(
            float(seller_state.get("pending_market_money", 0.0) or 0.0)
            + price,
            2,
        )

        _write_state(buyer_save, buyer_state)
        _write_state(seller_save, seller_state)

        db.session.commit()

        flash(
            f"Mua thành công {listing.player_name}! "
            "Cầu thủ đã được đưa vào Dự bị. "
            "OVR, cấp thẻ và giá trị được giữ nguyên."
        )

    except ValueError as exc:
        db.session.rollback()
        flash(str(exc))

    except Exception:
        db.session.rollback()
        flash(
            "Giao dịch chưa hoàn tất. Hệ thống đã giữ nguyên dữ liệu "
            "để tránh trừ tiền hoặc mua trùng."
        )

    return redirect(url_for("player_market.player_market"))


@player_market_bp.post("/player-market/withdraw/<int:listing_id>")
@login_required
def player_market_withdraw(listing_id):
    try:
        listing = (
            PlayerMarketListing.query
            .filter_by(
                id=listing_id,
                seller_id=current_user.id
            )
            .with_for_update()
            .first()
        )

        if not listing or listing.status != "active":
            raise ValueError(
                "Tin đăng không còn hiệu lực hoặc đã được mua."
            )

        save = _get_save(current_user.id, lock=True)

        if not save:
            raise ValueError("Không tìm thấy dữ liệu đội bóng.")

        state = _read_state(save)

        from sqlalchemy import update

        result = db.session.execute(
            update(PlayerMarketListing)
            .where(
                PlayerMarketListing.id == listing_id,
                PlayerMarketListing.seller_id == current_user.id,
                PlayerMarketListing.status == "active",
            )
            .values(status="withdrawn")
        )

        if result.rowcount != 1:
            raise ValueError(
                "Tin đăng đã được mua hoặc đã được thu hồi."
            )

        group = (
            listing.player_group
            if listing.player_group in {"bench", "extras"}
            else "bench"
        )

        # Tin đăng lưu nguyên bản dữ liệu của đúng thẻ đã rời CLB.
        # Không chặn thu hồi chỉ vì CLB có một thẻ khác trùng tên: các thẻ
        # cùng tên/mùa/cấp có thể là những bản sao hợp lệ trong bộ sưu tập.
        # Xóa dấu rời CLB trước khi trả cầu thủ về đội.
        _unmark_market_removed(state, listing.player_name)

        restored_player = copy.deepcopy(listing.player_data or {})
        if not isinstance(restored_player, dict):
            raise ValueError("Dữ liệu cầu thủ trong tin đăng không hợp lệ.")

        # A card with an impossible level (e.g. +585) would also break other
        # squad templates that display OVR using the supported +0..+8 table.
        # Normalize only when returning it to the squad so the game remains usable.
        try:
            restored_level = int(restored_player.get("level", 0) or 0)
        except (TypeError, ValueError, OverflowError):
            restored_level = 0
        restored_player["level"] = max(0, min(MAX_UPGRADE_LEVEL, restored_level))

        state.setdefault(group, []).append(restored_player)

        _write_state(save, state)
        db.session.commit()

        group_name = "Dự bị" if group == "bench" else "Cầu thủ khác"

        flash(
            f"Đã thu hồi tin đăng. "
            f"{listing.player_name} đã trở lại mục {group_name}."
        )

    except ValueError as exc:
        db.session.rollback()
        flash(str(exc))

    except Exception:
        db.session.rollback()
        flash("Không thể thu hồi tin đăng lúc này.")

    return redirect(url_for("player_market.player_market"))


@player_market_bp.post("/player-market/claim")
@login_required
def player_market_claim():
    save = _get_save(current_user.id, lock=True)

    if not save:
        return redirect(url_for("choose_club"))

    try:
        state = _read_state(save)

        pending = round(
            float(state.get("pending_market_money", 0.0) or 0.0),
            2
        )

        if pending <= 0:
            raise ValueError(
                "Bạn không có tiền chuyển nhượng đang chờ nhận."
            )

        state["budget"] = round(
            float(state.get("budget", 0.0)) + pending,
            2
        )

        state["pending_market_money"] = 0.0

        _write_state(save, state)
        db.session.commit()

        flash(
            f"Đã nhận {pending:.2f} M PC vào ngân sách CLB."
        )

    except ValueError as exc:
        db.session.rollback()
        flash(str(exc))

    except Exception:
        db.session.rollback()
        flash("Không thể nhận tiền lúc này.")

    return redirect(url_for("player_market.player_market"))
