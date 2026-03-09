'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export interface User {
    username: string;       // 工號 — used as namespace key for localStorage
    name: string;           // 姓名
    dpt: string;            // 部門
    title?: string;         // 職稱 (from MySQL)
    rank?: number | null;   // 職級 1~9 (1 = highest, null = unknown)
    canViewRecords?: boolean; // 是否有查閱員工紀錄的權限
}

interface UserContextType {
    user: User | null;
    login: (user: User) => void;
    logout: () => void;
}

const UserContext = createContext<UserContextType | undefined>(undefined);

const SESSION_KEY = 'user_session';

export function UserProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(() => {
        if (typeof window === 'undefined') return null;
        const saved = localStorage.getItem(SESSION_KEY);
        if (!saved) return null;
        try {
            return JSON.parse(saved) as User;
        } catch {
            return null;
        }
    });

    const login = (userData: User) => {
        localStorage.setItem(SESSION_KEY, JSON.stringify(userData));
        setUser(userData);
    };

    const logout = () => {
        localStorage.removeItem(SESSION_KEY);
        setUser(null);
    };

    return (
        <UserContext.Provider value={{ user, login, logout }}>
            {children}
        </UserContext.Provider>
    );
}

export function useUser() {
    const ctx = useContext(UserContext);
    if (!ctx) throw new Error('useUser must be used within a UserProvider');
    return ctx;
}
