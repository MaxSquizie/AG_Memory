package com.ahmemory.app

import android.app.Application
import android.util.Log
import com.ahmemory.app.data.AhRepository
import com.ahmemory.app.data.LiveAhRepository

class AhApplication : Application() {
    lateinit var repository: AhRepository
        private set

    override fun onCreate() {
        super.onCreate()
        repository = LiveAhRepository(this)
        Log.i(TAG, "runtime=live (core starts on first use)")
    }

    companion object {
        const val TAG = "AHMemory"
    }
}
