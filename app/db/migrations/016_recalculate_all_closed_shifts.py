from app.db.session import SessionLocal
from app.models.tables import Shift
from app.services.paycalc_service import compute_shift_calc


def main() -> None:
    db = SessionLocal()
    try:
        shift_ids = [
            sid
            for (sid,) in (
                db.query(Shift.shift_id)
                .filter(Shift.status == "CLOSED")
                .filter(Shift.check_in_ts.isnot(None), Shift.check_out_ts.isnot(None))
                .order_by(Shift.shift_id.asc())
                .all()
            )
        ]

        updated = 0
        failed: list[tuple[int, str]] = []

        for sid in shift_ids:
            try:
                compute_shift_calc(db, sid)
                db.commit()
                updated += 1
            except Exception as exc:
                db.rollback()
                failed.append((sid, str(exc)))

        print(f"Closed shifts scanned: {len(shift_ids)}")
        print(f"Closed shifts recalculated: {updated}")
        print(f"Closed shifts failed: {len(failed)}")
        for sid, err in failed:
            print(f"FAILED shift_id={sid}: {err}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
