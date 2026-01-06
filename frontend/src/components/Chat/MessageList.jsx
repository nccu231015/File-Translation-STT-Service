import React, { useEffect, useRef } from 'react';
import MessageItem from './MessageItem';

const TypingIndicator = () => (
    <div className="flex justify-start mb-4 animate-fade-in-up">
        <div className="bg-white border border-gray-200 shadow-sm rounded-2xl py-3 px-4 rounded-tl-none flex items-center gap-1">
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
        </div>
    </div>
);

const MessageList = ({ messages, isLoading }) => {
    const bottomRef = useRef(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, isLoading]);

    return (
        <div className="flex-1 overflow-y-auto p-4 bg-gray-50/50">
            <div className="max-w-3xl mx-auto">
                {messages.length === 0 && (
                    <div className="flex items-center justify-center h-full pt-20">
                        <div className="text-center text-gray-400">
                            <p className="text-xl font-medium mb-2">Welcome</p>
                            <p className="text-sm">Start recording to see transcription</p>
                        </div>
                    </div>
                )}
                {messages.map((msg, index) => (
                    <MessageItem key={index} {...msg} />
                ))}

                {isLoading && <TypingIndicator />}

                {/* Invisible element to scroll to */}
                <div ref={bottomRef} />
            </div>
        </div>
    );
};

export default MessageList;
