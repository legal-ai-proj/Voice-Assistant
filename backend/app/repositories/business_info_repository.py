"""
Data access for get_business_info -- read-only queries, no business
logic. Every query is scoped by branch_id (and chain_id where the data
lives at the chain level).
"""


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Branch, BranchHours, BranchSettings, Chain, Product, Service, Staff


async def get_branch_by_vapi_phone(db: AsyncSession, vapi_phone: str) -> Branch | None:
    """Look up a branch by its Vapi phone number. Used by the inbound
    call handler to resolve which branch a call came in on, so each
    branch's phone number routes to its own data without any hardcoding."""
    result = await db.execute(
        select(Branch).where(Branch.vapi_phone_number == vapi_phone, Branch.active.is_(True))
    )
    return result.scalar_one_or_none()


async def get_branch_with_chain(db: AsyncSession, branch_id: int) -> tuple[Branch, Chain] | None:
    result = await db.execute(select(Branch).where(Branch.id == branch_id, Branch.active.is_(True)))
    branch = result.scalar_one_or_none()
    if branch is None:
        return None
    chain_result = await db.execute(select(Chain).where(Chain.id == branch.chain_id))
    chain = chain_result.scalar_one_or_none()
    if chain is None:
        return None
    return branch, chain


async def get_branch_hours(db: AsyncSession, branch_id: int) -> list[BranchHours]:
    result = await db.execute(
        select(BranchHours).where(BranchHours.branch_id == branch_id).order_by(BranchHours.day_of_week)
    )
    return list(result.scalars().all())


async def get_active_services(db: AsyncSession, branch_id: int) -> list[Service]:
    result = await db.execute(
        select(Service).where(Service.branch_id == branch_id, Service.active.is_(True)).order_by(Service.name)
    )
    return list(result.scalars().all())


async def get_active_staff(db: AsyncSession, branch_id: int) -> list[Staff]:
    result = await db.execute(
        select(Staff).where(Staff.branch_id == branch_id, Staff.active.is_(True)).order_by(Staff.name)
    )
    return list(result.scalars().all())


async def get_active_products(db: AsyncSession, branch_id: int) -> list[Product]:
    result = await db.execute(
        select(Product).where(Product.branch_id == branch_id, Product.active.is_(True)).order_by(Product.name)
    )
    return list(result.scalars().all())


async def get_branch_settings(db: AsyncSession, branch_id: int) -> BranchSettings | None:
    result = await db.execute(select(BranchSettings).where(BranchSettings.branch_id == branch_id))
    return result.scalar_one_or_none()
