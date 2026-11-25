package xyz.mlxkj.crlbj.data

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import kotlinx.coroutines.flow.Flow
import xyz.mlxkj.crlbj.engine.DecodeEvent

/**
 * 解码历史库（Room，字段与桌面版 records 表同名同义）。
 *
 * 去重策略与桌面版 HistoryDb.insert 一致：uid 为主键，
 * 同 uid（2.5s 窗口内被更优记录替换）执行 REPLACE 更新。
 */
@Entity(tableName = "records", indices = [
    androidx.room.Index("timestamp"),
    androidx.room.Index("train"),
])
data class RecordEntity(
    @PrimaryKey val uid: String,
    val timestamp: Double,
    val timeStr: String,
    val train: String,
    val baseTrain: String,
    val prefix: String,
    val direction: String,
    val speed: String,
    val position: String,
    val loco: String,
    val locoCode: String,
    val route: String,
    val category: String,
    val latitude: Double?,
    val longitude: Double?,
    val isDetailed: Boolean,
    val routeValid: Boolean,
    val msgTypeError: Boolean,
    val rawAddr: Long,
    val rawFunc: Int,
    val rawBcd: String,
    val rawIsShort: Boolean,
    val rawIsMerged: Boolean,
    val rawIsStandalone: Boolean,
    val rssi: Double,
    val afcHz: Double,
    val afcErrHz: Double,
    val afcScore: Double,
    val etaSeconds: Double?,
    val etaTime: String,
    val etaDistanceKm: Double?,
    val etaStatus: String,
) {
    companion object {
        fun fromEvent(e: DecodeEvent) = RecordEntity(
            uid = e.uid.ifEmpty { "ev-${e.timestamp}" },
            timestamp = e.timestamp, timeStr = e.timeStr,
            train = e.train, baseTrain = e.baseTrain, prefix = e.prefix,
            direction = e.direction, speed = e.speed, position = e.position,
            loco = e.loco, locoCode = e.locoCode, route = e.route,
            category = e.category, latitude = e.latitude, longitude = e.longitude,
            isDetailed = e.isDetailed, routeValid = e.routeValid,
            msgTypeError = e.msgTypeError,
            rawAddr = e.rawAddr, rawFunc = e.rawFunc, rawBcd = e.rawBcd,
            rawIsShort = e.rawIsShort, rawIsMerged = e.rawIsMerged,
            rawIsStandalone = e.rawIsStandalone,
            rssi = e.rssi, afcHz = e.afcHz, afcErrHz = e.afcErrHz, afcScore = e.afcScore,
            etaSeconds = e.etaSeconds, etaTime = e.etaTime,
            etaDistanceKm = e.etaDistanceKm, etaStatus = e.etaStatus,
        )
    }
}

@Dao
interface RecordDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(record: RecordEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(records: List<RecordEntity>)

    @Query("SELECT * FROM records ORDER BY timestamp DESC LIMIT :limit")
    fun recent(limit: Int = 500): Flow<List<RecordEntity>>

    @Query("SELECT * FROM records ORDER BY timestamp DESC")
    suspend fun all(): List<RecordEntity>

    @Query("SELECT COUNT(*) FROM records")
    fun count(): Flow<Int>

    @Query("DELETE FROM records")
    suspend fun clear()

    /** 历史页多选删除（uid 主键，一次删若干条） */
    @Query("DELETE FROM records WHERE uid IN (:uids)")
    suspend fun deleteByUids(uids: List<String>)
}

@Database(entities = [RecordEntity::class], version = 1, exportSchema = false)
abstract class LbjDatabase : RoomDatabase() {
    abstract fun recordDao(): RecordDao

    companion object {
        @Volatile private var instance: LbjDatabase? = null

        fun get(context: Context): LbjDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext, LbjDatabase::class.java, "lbj_history.db"
                ).build().also { instance = it }
            }
    }
}
