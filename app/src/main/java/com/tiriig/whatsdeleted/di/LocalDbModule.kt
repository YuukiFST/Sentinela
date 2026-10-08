package com.tiriig.whatsdeleted.di

import android.app.Application
import androidx.room.Room
import com.tiriig.whatsdeleted.data.database.Database
import com.tiriig.whatsdeleted.data.database.MIGRATION_2_3
import com.tiriig.whatsdeleted.data.database.MIGRATION_3_4
import com.tiriig.whatsdeleted.data.database.MIGRATION_4_5
import com.tiriig.whatsdeleted.data.database.MIGRATION_5_6
import com.tiriig.whatsdeleted.data.database.MIGRATION_6_7
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object LocalDbModule {

    @Provides
    @Singleton
    fun provideAppDatabase(application: Application): Database {
        return Room
            .databaseBuilder(application, Database::class.java, "database")
            .addMigrations(MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5, MIGRATION_5_6, MIGRATION_6_7)
            .build()
    }
}