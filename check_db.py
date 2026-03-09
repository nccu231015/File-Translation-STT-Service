import asyncio
import aiomysql

async def main():
    pool = await aiomysql.create_pool(
        host="172.16.2.68", 
        port=3306, 
        user="aiadmin", 
        password="AIP@ssw0rd", 
        db="aiservice"
    )
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT EMPID, EMPNAME, DEPTNAME, DUTYNAME FROM JEB_HR WHERE EMPNAME LIKE '%鄭依玲%'")
            rows = await cur.fetchall()
            for r in rows:
                print(r)
    pool.close()
    await pool.wait_closed()

asyncio.run(main())
