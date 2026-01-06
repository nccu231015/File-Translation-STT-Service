import React from 'react';

const MessageItem = ({ role, content, type }) => {
    const isUser = role === 'user';

    return (
        <div className={`flex w-full mb-4 ${isUser ? 'justify-end' : 'justify-start'}`}>
            <div
                className={`max-w-[80%] rounded-2xl px-4 py-3 shadow-sm 
          ${isUser
                        ? 'bg-blue-600 text-white rounded-br-none'
                        : 'bg-white border border-gray-100 text-gray-800 rounded-bl-none'
                    }`}
            >
                <div className="text-sm">
                    {type === 'audio' && <div className="text-xs opacity-75 mb-1">🎤 Audio Transcribed</div>}

                    {type === 'file-result' ? (
                        <div>
                            <div className="text-xs opacity-75 mb-2 font-bold">📄 PDF Translation Result</div>
                            <div className="whitespace-pre-wrap leading-relaxed max-h-[400px] overflow-y-auto bg-gray-50 p-2 rounded border border-gray-100">
                                {content}
                            </div>
                            <div className="mt-2 text-xs text-blue-500">File downloaded automatically.</div>
                        </div>
                    ) : (
                        <div className="whitespace-pre-wrap leading-relaxed">{content}</div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default MessageItem;
