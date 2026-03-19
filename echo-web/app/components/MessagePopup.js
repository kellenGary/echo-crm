import React, { useState, useEffect } from 'react';
import { MessageCircle, X, Edit2, Check, Trash2 } from 'lucide-react';
import { Button } from "@/components/ui/button";

export default function FactPopup({ fact, onClose, onUpdate, onDelete }) {
    const [isEditing, setIsEditing] = useState(false);
    const [editedValue, setEditedValue] = useState('');
    const [editedCategory, setEditedCategory] = useState('');

    useEffect(() => {
        if (fact) {
            setEditedValue(fact.value);
            setEditedCategory(fact.category);
            setIsEditing(false);
        }
    }, [fact]);

    if (!fact) return null;

    const handleSave = () => {
        onUpdate({
            ...fact,
            value: editedValue,
            category: editedCategory
        });
        setIsEditing(false);
    };

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
            <div className="bg-background border border-primary/20 rounded-xl shadow-2xl p-6 max-w-md w-full animate-in fade-in zoom-in duration-200">
                <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                        <div className="bg-primary/20 rounded-full p-2">
                            <MessageCircle className="size-5 text-primary" />
                        </div>
                        <div>
                            {isEditing ? (
                                <input 
                                    className="bg-secondary/30 border-none text-[10px] font-bold uppercase tracking-widest text-primary w-full px-1 rounded"
                                    value={editedCategory}
                                    onChange={(e) => setEditedCategory(e.target.value)}
                                    autoFocus
                                />
                            ) : (
                                <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{fact.category}</div>
                            )}
                            <div className="text-lg font-bold">Intelligence Fact</div>
                        </div>
                    </div>
                    <div className="flex items-center gap-1">
                        {!isEditing && (
                            <Button variant="ghost" size="icon" className="size-8 text-muted-foreground hover:text-primary" onClick={() => setIsEditing(true)}>
                                <Edit2 className="size-4" />
                            </Button>
                        )}
                        <Button variant="ghost" size="icon" className="size-8 -mr-2 text-muted-foreground hover:text-destructive" onClick={onClose}>
                            <X className="size-4" />
                        </Button>
                    </div>
                </div>
                
                <div className="space-y-4">
                    <div className="bg-secondary/20 p-4 rounded-lg border border-border/50">
                        {isEditing ? (
                            <textarea 
                                className="w-full bg-transparent border-none text-sm leading-relaxed font-medium focus:ring-0 p-0 resize-none"
                                rows={3}
                                value={editedValue}
                                onChange={(e) => setEditedValue(e.target.value)}
                            />
                        ) : (
                            <div className="text-sm leading-relaxed font-medium">
                                {fact.value}
                            </div>
                        )}
                    </div>

                    {!isEditing && fact.source_quote && (
                        <div className="space-y-2">
                            <div className="text-[10px] font-bold uppercase tracking-tight text-muted-foreground">Original Signal Source</div>
                            <div className="text-xs text-muted-foreground italic border-l-2 border-primary/30 pl-3 py-1">
                                "{fact.source_quote}"
                            </div>
                        </div>
                    )}

                    <div className="flex items-center justify-between pt-2 border-t border-border/20">
                        <div className="text-[10px] monospace text-muted-foreground">CONFIDENCE: {fact.confidence?.toUpperCase()}</div>
                        <div className="flex gap-2">
                            {isEditing ? (
                                <>
                                    <Button variant="outline" size="sm" className="h-8 text-[10px] font-bold" onClick={() => setIsEditing(false)}>
                                        CANCEL
                                    </Button>
                                    <Button size="sm" className="h-8 text-[10px] font-bold gap-1.5" onClick={handleSave}>
                                        <Check className="size-3" /> SAVE CHANGES
                                    </Button>
                                </>
                            ) : (
                                <>
                                    {onDelete && (
                                        <Button variant="ghost" size="sm" className="h-8 text-[10px] font-bold text-destructive hover:text-destructive hover:bg-destructive/10" onClick={() => onDelete(fact)}>
                                            DELETE
                                        </Button>
                                    )}
                                    <Button size="sm" className="h-8 text-[10px] font-bold" onClick={onClose}>
                                        ACKNOWLEDGE
                                    </Button>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}